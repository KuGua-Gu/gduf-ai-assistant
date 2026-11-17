"""离线规则模型：在 mock 模式下替代真实大模型，验证编排链路而不联网。

它不是"假的智能"，而是测试替身：用与真实模型相同的 LLMResponse 结构返回工具调用，
让 orchestrator 的参数校验、确认卡片、查账统计、澄清追问等逻辑都能被确定性覆盖。
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.agent.categories import detect_category, normalize_month, parse_amount, parse_occurred_at, parse_period, today_in
from app.agent.llm_client import LLMResponse, ToolCall
from app.agent.schemas import TransactionDraft

_QUERY_KEYWORDS = ("多少", "几笔", "哪类", "哪个类别", "最多", "统计", "占比", "合计", "总共", "明细", "哪些", "查一下", "查查", "账单")
_RECORD_KEYWORDS = ("记一笔", "记账", "帮我记", "花了", "买了", "付了", "充了", "消费")
_BUDGET_SET_KEYWORDS = ("预算设", "设置预算", "预算改", "预算定", "预算为", "预算 ", "预算：")
_BUDGET_STATUS_KEYWORDS = ("预算还剩", "预算剩下", "预算用了", "预算超", "预算怎么样", "预算够", "超支")


class RuleBasedLLM:
    """与 LLMClient 同签名的最小可用实现（仅用于测试与无 Key 演示）。"""

    model = "rule-based-mock"

    def __init__(self, timezone: str = "Asia/Shanghai") -> None:
        self._timezone = timezone
        self._call_seq = 0
        self._usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    @property
    def configured(self) -> bool:
        return True

    @property
    def usage_totals(self) -> dict[str, int]:
        return dict(self._usage)

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> LLMResponse:
        user_index = self._last_user_index(messages)
        user_text = messages[user_index]["content"] if user_index >= 0 else ""
        tool_messages = [m for m in messages[user_index + 1 :] if m.get("role") == "tool"]

        if tool_messages:
            return LLMResponse(content=self._summarize(tool_messages[-1]["content"]), finish_reason="stop")

        tool_name, arguments, content = self._decide(user_text)
        if tool_name is None:
            return LLMResponse(content=content, finish_reason="stop")
        self._call_seq += 1
        return LLMResponse(
            content="",
            tool_calls=[ToolCall(id=f"mock_call_{self._call_seq}", name=tool_name, arguments=arguments)],
            finish_reason="tool_calls",
        )

    def chat_json(self, messages: list[dict[str, Any]], temperature: float = 0.0) -> dict[str, Any]:
        """离线模式不提供自由 JSON 生成，返回最后一次决策的结构化结果。"""
        tool_name, arguments, _ = self._decide(messages[-1]["content"] if messages else "")
        return {"tool": tool_name, "arguments": arguments}

    # ---------- 内部规则 ----------

    @staticmethod
    def _last_user_index(messages: list[dict[str, Any]]) -> int:
        for index in range(len(messages) - 1, -1, -1):
            if messages[index].get("role") == "user":
                return index
        return -1

    def _decide(self, text: str) -> tuple[str | None, dict[str, Any], str]:
        today = today_in(self._timezone)

        if any(word in text for word in ("忘了", "不知道", "记不清")) and any(
            keyword in text for keyword in _RECORD_KEYWORDS
        ):
            drafts = self._parse_drafts(text, today)
            return "create_transactions", {"transactions": [draft.model_dump(mode="json") for draft in drafts]}, ""

        if self._is_budget_set(text):
            amount = parse_amount(text)
            category = detect_category(text)
            scope = category or "total"
            return "set_budget", {
                "scope": scope,
                "amount": amount or 0,
                "month": self._budget_month(text, today),
            }, ""

        if self._is_budget_status(text):
            return "get_budget_status", {"month": self._budget_month(text, today)}, ""

        if self._is_query(text):
            category = detect_category(text)
            period = parse_period(text, today)
            if any(word in text for word in ("明细", "哪些", "买了什么", "查一下", "查查")):
                args: dict[str, Any] = {"limit": 20}
                if period:
                    args["start_date"], args["end_date"] = period[0].isoformat(), period[1].isoformat()
                if category:
                    args["category"] = category
                return "query_transactions", args, ""
            args = {"group_by": "category"}
            if period:
                args["start_date"], args["end_date"] = period[0].isoformat(), period[1].isoformat()
            if category:
                args["category"] = category
            return "get_stats", args, ""

        if self._is_record(text):
            drafts = self._parse_drafts(text, today)
            return "create_transactions", {"transactions": [draft.model_dump(mode="json") for draft in drafts]}, ""

        return None, {}, "我可以帮你记账、查账和设置预算。比如直接说「午饭 25 元」，或者问「这个月餐饮花了多少」。"

    @staticmethod
    def _is_budget_set(text: str) -> bool:
        if parse_amount(text) is None:
            return False
        return any(keyword in text for keyword in _BUDGET_SET_KEYWORDS) or ("预算" in text and "多少" not in text and "还剩" not in text)

    @staticmethod
    def _is_budget_status(text: str) -> bool:
        return any(keyword in text for keyword in _BUDGET_STATUS_KEYWORDS) or ("预算" in text and ("还剩" in text or "用了" in text or "超" in text))

    @staticmethod
    def _is_query(text: str) -> bool:
        return any(keyword in text for keyword in _QUERY_KEYWORDS)

    @staticmethod
    def _is_record(text: str) -> bool:
        if parse_amount(text) is not None:
            return True
        return any(keyword in text for keyword in _RECORD_KEYWORDS)

    @staticmethod
    def _budget_month(text: str, today) -> str:
        return normalize_month(text, today)

    def _parse_drafts(self, text: str, today) -> list[TransactionDraft]:
        occurred_at = parse_occurred_at(text, today) or today
        note = "和同事 AA" if "AA" in text.upper() or "aa" in text else ""
        segments = [part for part in re.split(r"[，,；;、]", text) if part.strip()]
        drafts: list[TransactionDraft] = []

        for segment in segments:
            amount = parse_amount(segment)
            if amount is None:
                continue
            category = detect_category(segment) or detect_category(text)
            drafts.append(
                TransactionDraft(
                    amount=amount,
                    category=category,
                    merchant=segment.strip()[:30],
                    occurred_at=occurred_at,
                    note=note,
                )
            )

        if not drafts:
            drafts.append(
                TransactionDraft(
                    amount=parse_amount(text),
                    category=detect_category(text),
                    merchant=text.strip()[:30],
                    occurred_at=occurred_at,
                    note=note,
                    confidence=0.6 if parse_amount(text) is None else 1.0,
                )
            )
        return drafts

    @staticmethod
    def _summarize(tool_content: str) -> str:
        """把工具结果转成一句用户可读的回复。"""
        try:
            payload = json.loads(tool_content)
        except (TypeError, json.JSONDecodeError):
            return "查询完成了，但没有拿到可读的数据。"
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, dict) and "items" in data and "total" in data:
            items = data.get("items") or []
            head = f"共 {float(data.get('total', 0)):.2f} 元"
            if items:
                detail = "，".join(f"{item.get('key')} {float(item.get('amount', 0)):.2f} 元" for item in items[:3])
                return f"{head}，其中 {detail}。"
            return f"{head}，这段时间没有记录。"
        if isinstance(data, dict) and "count" in data:
            rows = data.get("items") or []
            total = sum(float(row.get("amount", 0)) for row in rows)
            return f"共查到 {data.get('count', 0)} 笔，合计 {total:.2f} 元。"
        if isinstance(data, dict) and "total_spent" in data:
            items = data.get("items") or []
            if items:
                item = items[0]
                label = "总预算" if item.get("scope") == "total" else str(item.get("scope"))
                status_text = {"exceeded": "已经超支", "warning": "已接近上限", "normal": "预算充足"}.get(item.get("status"), "预算正常")
                return (
                    f"{data.get('month', '本月')} {label}预算 {float(item.get('budget', 0)):.2f} 元，"
                    f"已花 {float(item.get('spent', 0)):.2f} 元，{status_text}。"
                )
            return f"本月已花 {float(data.get('total_spent', 0)):.2f} 元，还没有设置预算。"
        if isinstance(data, dict) and "scope" in data and "amount" in data:
            label = "总预算" if data.get("scope") == "total" else str(data.get("scope"))
            return f"已设置 {data.get('month', '本月')} {label}预算 {float(data.get('amount', 0)):.2f} 元。"
        return "已经处理好了。"
