"""Agent 编排器：意图路由、工具调用循环、草稿确认、多轮澄清与异常兜底。"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date

from app.agent.categories import CATEGORIES, detect_category, normalize_category, parse_amount, parse_occurred_at, today_in
from app.agent.errors import AgentError, ContextOverflowError, LLMUnavailableError, TOOL_RETRY_EXCEEDED_MESSAGE
from app.agent.llm_client import LLMClient, LLMResponse
from app.agent.memory import MemoryStore
from app.agent.prompts import CLARIFY_LIMIT_MESSAGE, CLARIFY_TEMPLATES, build_system_prompt
from app.agent.safety import REFUSAL_REPLY, detect_violation
from app.agent.schemas import (
    ChatResponse,
    Intent,
    PendingAction,
    TransactionDraft,
    TransactionPreview,
    TransactionSource,
)
from app.agent.tools import ToolRegistry, build_default_registry
from app.config import Settings, get_settings
from app.services.contracts import OcrService, TransactionService
from app.services.stubs import InMemoryTransactionService

logger = logging.getLogger("app.agent.orchestrator")

WEEKDAYS_CN = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")
CONFIRM_WORDS = {"确认", "确认入库", "提交", "入库", "对", "是的", "没错"}
CANCEL_WORDS = {"算了", "取消", "不用了", "先不记了"}
QUERY_HINTS = ("多少", "几笔", "哪类", "最多", "统计", "占比", "合计", "明细", "哪些", "查一下", "查查", "账单")
BUDGET_HINTS = ("预算",)
MAX_CLARIFY_ROUNDS = 2


class AgentOrchestrator:
    """把一条用户消息变成：确认卡片、统计回复或兜底话术。"""

    def __init__(
        self,
        llm: LLMClient | None = None,
        transactions: TransactionService | None = None,
        ocr: OcrService | None = None,
        memory: MemoryStore | None = None,
        registry: ToolRegistry | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.transactions = transactions or InMemoryTransactionService()
        self.ocr = ocr
        if llm is not None:
            self.llm = llm
        elif self.settings.llm_configured:
            self.llm = LLMClient(self.settings)
        else:
            # 未配置 Key 时降级为离线规则引擎，保证应用仍可启动与演示（不联网）
            from app.agent.mock_llm import RuleBasedLLM

            logger.warning("未配置 LLM_API_KEY，Agent 使用离线规则模式（仅演示，能力有限）")
            self.llm = RuleBasedLLM(self.settings.timezone)  # type: ignore[assignment]
        self.registry = registry or build_default_registry(self.transactions, self.ocr, timezone=self.settings.timezone)
        self.memory = memory or MemoryStore(
            self.settings.resolved_db_path,
            window=self.settings.agent_memory_window,
            timezone=self.settings.timezone,
        )
        self.max_tool_calls = max(1, int(self.settings.agent_max_tool_calls))

    # ---------- 对外入口 ----------

    def chat(self, session_id: str | None, message: str, image_id: str | None = None) -> ChatResponse:
        """处理一次用户输入。"""
        trace_id = uuid.uuid4().hex[:12]
        sid = self.memory.get_or_create(session_id)
        text = (message or "").strip()
        today = today_in(self.settings.timezone)
        log_text = text if not image_id else f"[图片 {image_id}] {text}"
        self.memory.append(sid, "user", log_text)
        state = self.memory.get_state(sid)

        violation = detect_violation(text)
        if violation:
            logger.info("trace=%s safety violation=%s", trace_id, violation)
            return self._finish(sid, REFUSAL_REPLY, Intent.REFUSE, trace_id)

        if image_id:
            return self._handle_image(sid, text, image_id, today, trace_id)

        pending = state.get("pending_draft")
        if pending:
            response = self._handle_pending(sid, text, pending, state.get("asks", {}), today, trace_id)
            if response is not None:
                return response

        return self._run_llm(sid, today, trace_id)

    def confirm(self, session_id: str, actions: list[PendingAction]) -> tuple[int, int, str, str]:
        """确认卡片落库，返回 (成功数, 失败数, 回复, trace_id)。"""
        trace_id = uuid.uuid4().hex[:12]
        sid = self.memory.get_or_create(session_id)
        created = 0
        failed = 0
        for action in actions:
            result = self._execute_action(action, trace_id)
            if result.ok:
                created += 1
            else:
                failed += 1
                logger.warning("trace=%s confirm failed action=%s error=%s", trace_id, action.action, result.error)

        if created:
            reply = f"已入账 {created} 笔。" + (f"另有 {failed} 笔未成功。" if failed else "")
            self.memory.set_state(sid, {})
        else:
            reply = "这次没有入账成功，请检查金额、类别和日期是否完整。"
        self.memory.append(sid, "assistant", reply)
        return created, failed, reply, trace_id

    # ---------- 待补齐草稿 ----------

    def _handle_pending(
        self,
        sid: str,
        text: str,
        pending: dict,
        asks: dict[str, int],
        today: date,
        trace_id: str,
    ) -> ChatResponse | None:
        """有未完成草稿时，优先把本轮输入当作补充信息；换话题则放弃草稿。"""
        if text in CANCEL_WORDS:
            self.memory.set_state(sid, {})
            return self._finish(sid, "好的，这笔先不记了。", Intent.CHITCHAT, trace_id)

        if self._looks_like_new_topic(text):
            self.memory.set_state(sid, {})
            return None

        if text in CONFIRM_WORDS:
            draft = TransactionDraft.model_validate(pending)
            action = PendingAction(action="create", draft=draft)
            return self._finish(
                sid,
                "请在确认卡片上点击「确认」完成入账。",
                Intent.CONFIRM_ACTION,
                trace_id,
                pending_actions=[action],
            )

        draft = TransactionDraft.model_validate(pending)
        self._merge_clarification(draft, text, today)
        missing = draft.missing_fields()
        if missing:
            return self._ask_clarify(sid, draft, asks, missing, trace_id)
        return self._finish_pending(sid, [PendingAction(action="create", draft=draft)], trace_id)

    def _merge_clarification(self, draft: TransactionDraft, text: str, today: date) -> None:
        """把补充信息合并进草稿，只填空缺字段，不覆盖用户已确认的内容。"""
        amount = parse_amount(text)
        if amount is not None and draft.amount is None:
            draft.amount = amount
        category = detect_category(text)
        if draft.category is None:
            if category:
                draft.category = category
            elif text.strip() in CATEGORIES:
                draft.category = text.strip()
        occurred_at = parse_occurred_at(text, today)
        if occurred_at is not None and draft.occurred_at is None:
            draft.occurred_at = occurred_at
        if draft.occurred_at is None and draft.source != TransactionSource.OCR:
            draft.occurred_at = today
        if ("AA" in text.upper() or "aa" in text) and "AA" not in draft.note.upper():
            draft.note = (draft.note + "，和同事 AA").strip("，") if draft.note else "和同事 AA"

    def _ask_clarify(
        self,
        sid: str,
        draft: TransactionDraft,
        asks: dict[str, int],
        missing: list[str],
        trace_id: str,
    ) -> ChatResponse:
        """按最关键的缺失字段追问，同一字段超过两轮则给出固定引导。"""
        field = missing[0]
        asks = dict(asks)
        asks[field] = asks.get(field, 0) + 1
        if asks[field] > MAX_CLARIFY_ROUNDS:
            self.memory.set_state(sid, {})
            return self._finish(sid, CLARIFY_LIMIT_MESSAGE, Intent.RECORD_EXPENSE, trace_id)

        self.memory.set_state(
            sid,
            {"pending_draft": draft.model_dump(mode="json"), "asks": asks},
        )
        known = []
        if draft.amount is not None:
            known.append(f"金额 {draft.amount:.2f} 元")
        if draft.category:
            known.append(draft.category)
        prefix = f"好的，已记下{'、'.join(known)}。" if known else ""
        return self._finish(sid, prefix + CLARIFY_TEMPLATES[field], Intent.RECORD_EXPENSE, trace_id)

    def _finish_pending(self, sid: str, actions: list[PendingAction], trace_id: str) -> ChatResponse:
        self.memory.set_state(sid, {})
        return self._finish(
            sid,
            self._pending_reply(actions),
            Intent.RECORD_EXPENSE,
            trace_id,
            pending_actions=actions,
        )

    # ---------- 图片 / OCR ----------

    def _handle_image(self, sid: str, text: str, image_id: str, today: date, trace_id: str) -> ChatResponse:
        """图片链路：OCR 结果直接生成草稿，缺失字段走澄清或确认。"""
        if self.ocr is None:
            return self._finish(sid, "图片识别能力暂未接入，可以先手动告诉我金额和类别。", Intent.RECORD_EXPENSE, trace_id)

        try:
            result = self.ocr.recognize(image_id)
        except Exception as exc:  # noqa: BLE001 - OCR 属外部服务
            logger.warning("trace=%s ocr failed: %s", trace_id, exc)
            return self._finish(sid, "这张图片暂时识别不了，可以手动告诉我金额和商户。", Intent.RECORD_EXPENSE, trace_id)

        draft = TransactionDraft(
            amount=result.amount,
            category=detect_category(result.merchant) or None,
            merchant=result.merchant,
            occurred_at=result.occurred_at,
            note=text,
            source=TransactionSource.OCR,
            confidence=result.confidence,
            needs_review=[
                field
                for field, value in (
                    ("amount", result.amount),
                    ("category", detect_category(result.merchant)),
                    ("occurred_at", result.occurred_at),
                )
                if value is None
            ],
        )
        missing = draft.missing_fields()
        if missing:
            return self._ask_clarify(sid, draft, {}, missing, trace_id)
        return self._finish_pending(sid, [PendingAction(action="create", draft=draft)], trace_id)

    # ---------- 模型 + 工具循环 ----------

    def _run_llm(self, sid: str, today: date, trace_id: str) -> ChatResponse:
        messages = [
            {"role": "system", "content": build_system_prompt(today, WEEKDAYS_CN[today.weekday()])},
            *self.memory.context(sid),
        ]
        tool_names: list[str] = []
        pending_actions: list[PendingAction] = []
        write_failures = 0
        tool_calls_used = 0

        while tool_calls_used < self.max_tool_calls:
            try:
                response = self.llm.chat(messages, tools=self.registry.to_openai_tools())
            except AgentError as exc:
                return self._fallback(sid, exc, trace_id)

            if not response.tool_calls:
                reply = response.content.strip() or "我没太理解，可以再说得具体一点吗？"
                return self._finish(sid, reply, self._infer_intent(tool_names, bool(pending_actions)), trace_id,
                                    pending_actions=pending_actions)

            messages.append(self._assistant_tool_message(response))
            incomplete: TransactionDraft | None = None

            for call in response.tool_calls:
                if tool_calls_used >= self.max_tool_calls:
                    logger.warning("trace=%s 工具调用次数超限", trace_id)
                    return self._finish(sid, TOOL_RETRY_EXCEEDED_MESSAGE, Intent.CHITCHAT, trace_id)
                tool_calls_used += 1
                spec = self.registry.get(call.name)
                tool_names.append(call.name)
                if spec is None:
                    messages.append(self._tool_message(call.id, {"ok": False, "error": f"未知工具：{call.name}"}))
                    continue

                if spec.write_action:
                    actions, missing = self.registry.to_pending_actions(
                        call.name, call.arguments, trace_id=trace_id
                    )
                    if missing and spec.write_action == "create":
                        args, failure = self.registry.validate(call.name, call.arguments)
                        if failure is not None:
                            write_failures += 1
                            messages.append(self._tool_message(call.id, failure.model_dump(mode="json")))
                            continue
                        drafts = getattr(args, "transactions", [])
                        incomplete = next((item for item in drafts if item.missing_fields()), None)
                        messages.append(self._tool_message(call.id, {"ok": False, "error": "草稿字段不完整，需要向用户追问"}))
                        continue
                    pending_actions.extend(actions)
                    messages.append(self._tool_message(call.id, {"ok": True, "data": "已生成待确认卡片，等待用户确认"}))
                else:
                    result = self.registry.execute(call.name, call.arguments, trace_id=trace_id)
                    messages.append(self._tool_message(call.id, result.model_dump(mode="json")))

            if incomplete is not None:
                return self._ask_clarify(sid, incomplete, {}, incomplete.missing_fields(), trace_id)

            if write_failures >= MAX_CLARIFY_ROUNDS:
                return self._finish(sid, TOOL_RETRY_EXCEEDED_MESSAGE, Intent.RECORD_EXPENSE, trace_id)

            if pending_actions:
                reply = response.content.strip() or self._pending_reply(pending_actions)
                return self._finish(sid, reply, Intent.RECORD_EXPENSE, trace_id,
                                    pending_actions=pending_actions)

        logger.warning("trace=%s 工具调用次数超限", trace_id)
        return self._finish(sid, TOOL_RETRY_EXCEEDED_MESSAGE, Intent.CHITCHAT, trace_id)

    # ---------- 响应组装 ----------

    def _finish(
        self,
        sid: str,
        reply: str,
        intent: Intent,
        trace_id: str,
        pending_actions: list[PendingAction] | None = None,
    ) -> ChatResponse:
        actions = pending_actions or []
        previews = [self._to_preview(action.draft) for action in actions if action.draft is not None]
        self.memory.append(sid, "assistant", reply)
        logger.info("trace=%s intent=%s actions=%d reply_len=%d", trace_id, intent.value, len(actions), len(reply))
        return ChatResponse(
            session_id=sid,
            reply=reply,
            intent=intent,
            pending_actions=actions,
            transaction_preview=previews,
            confirm_required=bool(actions),
            trace_id=trace_id,
        )

    def _fallback(self, sid: str, exc: AgentError, trace_id: str) -> ChatResponse:
        logger.warning("trace=%s fallback code=%s detail=%s", trace_id, exc.code, exc.detail)
        if isinstance(exc, LLMUnavailableError) and "context" in exc.detail.lower():
            exc = ContextOverflowError(exc.detail)
        return self._finish(sid, exc.user_message, Intent.CHITCHAT, trace_id)

    def _execute_action(self, action: PendingAction, trace_id: str = ""):
        if action.action == "create" and action.draft is not None:
            if action.draft.missing_fields():
                from app.agent.schemas import ToolResult

                return ToolResult.failure("草稿字段不完整")
            return self.registry.execute(
                "create_transactions",
                {"transactions": [action.draft.model_dump(mode="json")]},
                trace_id=trace_id,
            )
        if action.action == "update" and action.transaction_id is not None:
            return self.registry.execute(
                "update_transaction",
                {"transaction_id": action.transaction_id, "patch": action.patch or {}},
                trace_id=trace_id,
            )
        if action.action == "delete" and action.transaction_id is not None:
            return self.registry.execute(
                "delete_transaction",
                {"transaction_id": action.transaction_id},
                trace_id=trace_id,
            )
        from app.agent.schemas import ToolResult

        return ToolResult.failure("不支持的确认动作")

    @staticmethod
    def _to_preview(draft: TransactionDraft | None) -> TransactionPreview:
        assert draft is not None
        return TransactionPreview(
            amount=draft.amount,
            category=draft.category,
            merchant=draft.merchant,
            occurred_at=draft.occurred_at,
            note=draft.note,
            source=draft.source.value,
            needs_review=draft.needs_review,
        )

    @staticmethod
    def _pending_reply(actions: list[PendingAction]) -> str:
        parts = []
        for action in actions:
            draft = action.draft
            if draft is None:
                continue
            amount = f"{draft.amount:.2f} 元" if draft.amount is not None else "金额待补"
            category = draft.category or "类别待补"
            occurred = f"{draft.occurred_at.month}月{draft.occurred_at.day}日" if draft.occurred_at else "日期待补"
            extra = f"，备注「{draft.note}」" if draft.note else ""
            parts.append(f"{category} {amount}（{occurred}）{extra}")
        count = len(parts)
        prefix = "已为你生成 1 张确认卡片：" if count == 1 else f"已为你生成 {count} 张确认卡片："
        return prefix + "；".join(parts) + "。确认后才会入账。"

    @staticmethod
    def _assistant_tool_message(response: LLMResponse) -> dict:
        return {
            "role": "assistant",
            "content": response.content or None,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, ensure_ascii=False),
                    },
                }
                for call in response.tool_calls
            ],
        }

    @staticmethod
    def _tool_message(tool_call_id: str, payload: dict) -> dict:
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": json.dumps(payload, ensure_ascii=False, default=str),
        }

    @staticmethod
    def _infer_intent(tool_names: list[str], has_pending: bool) -> Intent:
        names = set(tool_names)
        if has_pending or "create_transactions" in names:
            return Intent.RECORD_EXPENSE
        if names & {"update_transaction", "delete_transaction"}:
            return Intent.CONFIRM_ACTION
        if names & {"get_stats", "query_transactions"}:
            return Intent.QUERY_STATS
        if names & {"set_budget", "get_budget_status"}:
            return Intent.MANAGE_BUDGET
        return Intent.CHITCHAT

    @staticmethod
    def _looks_like_new_topic(text: str) -> bool:
        return any(hint in text for hint in QUERY_HINTS + BUDGET_HINTS)
