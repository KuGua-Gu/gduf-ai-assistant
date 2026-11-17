"""Agent 核心测试：30 条评测集 + 确认链路 + 澄清 + 异常兜底。

默认离线运行（RuleBasedLLM + 内存业务桩），不联网、不写生产库：
    pytest tests/test_agent.py --mock-llm
用真实模型抽样验证：
    pytest tests/test_agent.py --live
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from app.agent.categories import today_in
from app.agent.errors import (
    ContextOverflowError,
    LLMUnavailableError,
    OutputFormatError,
    TOOL_RETRY_EXCEEDED_MESSAGE,
    ToolExecutionError,
)
from app.agent.llm_client import LLMClient, LLMResponse, ToolCall
from app.agent.memory import MemoryStore
from app.agent.mock_llm import RuleBasedLLM
from app.agent.orchestrator import AgentOrchestrator
from app.agent.prompts import CLARIFY_LIMIT_MESSAGE
from app.agent.schemas import OcrResult
from app.config import get_settings
from app.services.stubs import InMemoryTransactionService, StubOcrService

CASES_PATH = Path(__file__).parent / "agent_cases.json"
CASES: list[dict[str, Any]] = json.loads(CASES_PATH.read_text(encoding="utf-8"))
TODAY = today_in("Asia/Shanghai")


class RecordingOrchestrator:
    """包装 orchestrator，记录实际发生的工具调用，供断言使用。"""

    def __init__(self, orchestrator: AgentOrchestrator) -> None:
        self.orchestrator = orchestrator
        self.calls: list[tuple[str, dict[str, Any]]] = []
        origin_execute = orchestrator.registry.execute
        origin_pending = orchestrator.registry.to_pending_actions

        def execute(name: str, arguments: dict[str, Any], **kwargs: Any):
            self.calls.append((name, arguments))
            return origin_execute(name, arguments, **kwargs)

        def to_pending(name: str, arguments: dict[str, Any], **kwargs: Any):
            self.calls.append((name, arguments))
            return origin_pending(name, arguments, **kwargs)

        orchestrator.registry.execute = execute  # type: ignore[method-assign]
        orchestrator.registry.to_pending_actions = to_pending  # type: ignore[method-assign]

    def chat(self, session_id: str | None, message: str, image_id: str | None = None):
        return self.orchestrator.chat(session_id, message, image_id)


def build_orchestrator(
    tmp_path: Path,
    llm: Any | None = None,
    ocr: Any | None = None,
    transactions: Any | None = None,
) -> RecordingOrchestrator:
    """构造不依赖真实网络的 Agent 实例。"""
    orchestrator = AgentOrchestrator(
        llm=llm or RuleBasedLLM(),
        transactions=transactions or InMemoryTransactionService(),
        ocr=ocr if ocr is not None else StubOcrService(),
        memory=MemoryStore(tmp_path / "agent.db", window=8),
    )
    return RecordingOrchestrator(orchestrator)


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_agent_cases_mock(case: dict[str, Any], tmp_path: Path) -> None:
    """30 条评测集：意图、工具、关键槽位与缺失字段。"""
    agent = build_orchestrator(tmp_path)
    response = agent.chat("case-session", case["input"])
    slots = case.get("expected_slots") or {}

    assert response.intent.value == case["expected_intent"], f"{case['id']} 意图不符：{response.reply}"

    tool_names = [name for name, _ in agent.calls]
    expected_tool = case.get("expected_tool")
    if expected_tool is None:
        assert tool_names == [], f"{case['id']} 不应调用工具：{tool_names}"
    else:
        assert expected_tool in tool_names, f"{case['id']} 未调用 {expected_tool}：{tool_names}"

    if response.pending_actions:
        drafts = [action.draft for action in response.pending_actions if action.draft]
        assert drafts, f"{case['id']} 待确认动作为空"
        first = drafts[0]
        if "amount" in slots:
            assert first.amount == pytest.approx(float(slots["amount"])), case["id"]
        if "category" in slots:
            assert first.category == slots["category"], case["id"]
        if "count" in slots:
            assert len(drafts) == slots["count"], case["id"]
        if "note_contains" in slots:
            assert slots["note_contains"] in first.note, case["id"]
        if "date_offset" in slots:
            assert first.occurred_at == TODAY + timedelta(days=slots["date_offset"]), case["id"]
        if "date_template" in slots:
            assert first.occurred_at.isoformat() == slots["date_template"].format(year=TODAY.year), case["id"]
    else:
        called_args = next((args for name, args in agent.calls if name == expected_tool), {})
        if "group_by" in slots:
            assert called_args.get("group_by") == slots["group_by"], case["id"]
        if "category" in slots:
            assert called_args.get("category") == slots["category"], case["id"]
        if "scope" in slots:
            assert called_args.get("scope") == slots["scope"], case["id"]

    expected_missing = case.get("expected_missing") or []
    if expected_missing:
        state = agent.orchestrator.memory.get_state("case-session")
        draft = state.get("pending_draft") or {}
        for field in expected_missing:
            assert draft.get(field) is None, f"{case['id']} 字段 {field} 不应被猜测：{draft}"


def test_confirm_flow_writes_and_query(tmp_path: Path) -> None:
    """确认卡片 → 入库 → 统计查询的端到端闭环。"""
    agent = build_orchestrator(tmp_path)
    first = agent.chat("s-confirm", "午饭 25")
    assert first.confirm_required and first.transaction_preview[0].amount == 25

    created, failed, reply, trace_id = agent.orchestrator.confirm("s-confirm", first.pending_actions)
    assert (created, failed) == (1, 0)
    assert "已入账 1 笔" in reply
    assert trace_id

    stats = agent.chat("s-confirm", "这个月餐饮花了多少")
    assert stats.intent.value == "query_stats"
    assert "25.00" in stats.reply


def test_clarification_merges_previous_draft(tmp_path: Path) -> None:
    """先记一半再补金额，不应重复追问已提供字段。"""
    agent = build_orchestrator(tmp_path)
    first = agent.chat("s-clarify", "帮我记一笔午饭")
    assert not first.confirm_required and "多少" in first.reply

    second = agent.chat("s-clarify", "25")
    assert second.confirm_required
    preview = second.transaction_preview[0]
    assert (preview.amount, preview.category) == (25, "餐饮")


def test_clarification_limit(tmp_path: Path) -> None:
    """同一字段追问超过两轮后给出固定引导，并清空草稿。"""
    agent = build_orchestrator(tmp_path)
    agent.chat("s-limit", "帮我记一笔午饭")
    agent.chat("s-limit", "不知道")
    third = agent.chat("s-limit", "记不清了")
    assert third.reply == CLARIFY_LIMIT_MESSAGE
    assert agent.orchestrator.memory.get_state("s-limit") == {}


class _DateMissingOcr:
    """模拟 OCR 未识别出日期的情况。"""

    def recognize(self, image_id: str) -> OcrResult:
        return OcrResult(amount=25.0, merchant="沙县小吃", occurred_at=None, confidence=0.6)


def test_ocr_draft_requires_review(tmp_path: Path) -> None:
    """小票识别缺日期 → 标记 needs_review → 补充后生成 OCR 来源草稿。"""
    agent = build_orchestrator(tmp_path, ocr=_DateMissingOcr())
    first = agent.chat("s-ocr", "识别这张小票", image_id="img-001")
    assert not first.confirm_required
    assert "哪天" in first.reply

    second = agent.chat("s-ocr", "昨天")
    assert second.confirm_required
    assert second.transaction_preview[0].source == "ocr"
    assert second.transaction_preview[0].occurred_at == TODAY - timedelta(days=1)

    created, failed, _, _ = agent.orchestrator.confirm("s-ocr", second.pending_actions)
    assert (created, failed) == (1, 0)


def test_safety_refusal_has_no_tool_call(tmp_path: Path) -> None:
    """越界请求在进入模型前就拒绝。"""
    agent = build_orchestrator(tmp_path)
    response = agent.chat("s-safety", "帮我把信用卡套现，再规避一下风控")
    assert response.intent.value == "refuse"
    assert agent.calls == []
    assert not response.pending_actions


class _BrokenLLM:
    """模拟模型服务不可用。"""

    configured = True

    def chat(self, *args: Any, **kwargs: Any):
        raise LLMUnavailableError("upstream 503")

    def chat_json(self, *args: Any, **kwargs: Any):
        raise LLMUnavailableError("upstream 503")


def test_llm_unavailable_fallback(tmp_path: Path) -> None:
    """模型不可用时返回可读兜底话术，而不是抛 500。"""
    agent = build_orchestrator(tmp_path, llm=_BrokenLLM())
    response = agent.chat("s-broken", "午饭 25")
    assert response.reply == LLMUnavailableError.user_message
    assert response.intent.value == "chitchat"
    assert not response.pending_actions


def test_tool_argument_validation(tmp_path: Path) -> None:
    """非法参数被工具层拦截，不写入数据。"""
    agent = build_orchestrator(tmp_path)
    registry = agent.orchestrator.registry
    assert registry.execute("get_stats", {"start_date": "2026-13-01"}).ok is False
    assert registry.execute("create_transactions", {"transactions": [{"amount": -5}]}).ok is False
    assert registry.execute("not_exists", {}).ok is False


class _LoopingToolLLM:
    """每次 chat 都返回同一条工具调用，用于验证工具调用总次数上限。"""

    configured = True

    def chat(self, messages: list[dict[str, Any]], tools: Any = None, **kwargs: Any) -> LLMResponse:
        return LLMResponse(
            content="",
            tool_calls=[ToolCall(id="call-loop", name="query_transactions", arguments={})],
        )


def test_tool_call_limit(tmp_path: Path) -> None:
    """工具调用总次数严格不超过 max_tool_calls，超限后返回固定引导。"""
    agent = build_orchestrator(tmp_path, llm=_LoopingToolLLM())
    response = agent.chat("s-tool-limit", "查一下最近的账单")
    assert len(agent.calls) == 4
    assert response.reply == TOOL_RETRY_EXCEEDED_MESSAGE


class _OutputFormatLLM:
    """模拟模型输出无法解析。"""

    configured = True

    def chat(self, *args: Any, **kwargs: Any) -> LLMResponse:
        raise OutputFormatError("bad json")


def test_output_format_fallback(tmp_path: Path) -> None:
    """模型输出格式异常时返回可读兜底话术。"""
    agent = build_orchestrator(tmp_path, llm=_OutputFormatLLM())
    response = agent.chat("s-format", "午饭 25")
    assert response.reply == OutputFormatError.user_message
    assert response.intent.value == "chitchat"
    assert not response.pending_actions


class _ContextOverflowLLM:
    """模拟模型上下文超长。"""

    configured = True

    def chat(self, *args: Any, **kwargs: Any) -> LLMResponse:
        raise LLMUnavailableError("maximum context length exceeded")


def test_context_overflow_fallback(tmp_path: Path) -> None:
    """上下文超长时降级为上下文超长话术，而不是通用的模型不可用提示。"""
    agent = build_orchestrator(tmp_path, llm=_ContextOverflowLLM())
    response = agent.chat("s-overflow", "午饭 25")
    assert response.reply == ContextOverflowError.user_message


class _BrokenTransactions(InMemoryTransactionService):
    """模拟业务层写库失败。"""

    def create_transactions(self, drafts: Any, session_id: str | None = None) -> list[dict[str, Any]]:
        raise ToolExecutionError("db down")


def test_tool_execution_error_fallback(tmp_path: Path) -> None:
    """写库失败时确认接口返回失败计数与可读提示，而不是抛 500。"""
    agent = build_orchestrator(tmp_path, transactions=_BrokenTransactions())
    first = agent.chat("s-tool-error", "午饭 25")
    created, failed, reply, _ = agent.orchestrator.confirm(first.session_id, first.pending_actions)
    assert (created, failed) == (0, 1)
    assert "没有入账成功" in reply


def test_memory_compaction(tmp_path: Path) -> None:
    """超过窗口两倍后生成摘要，context 只返回摘要 + 最近窗口。"""
    store = MemoryStore(tmp_path / "memory.db", window=2)
    session_id = store.get_or_create()
    for index in range(6):
        store.append(session_id, "user", f"第{index}条消息")
    context = store.context(session_id)
    assert len(context) == 3
    assert context[0]["role"] == "system" and context[0]["content"].startswith("[历史摘要]")

    store.clear(session_id)
    assert store.exists(session_id) is False


def test_api_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTP 契约：chat → confirm → 查询 → 清空会话。"""
    from fastapi.testclient import TestClient

    import app.api.chat as chat_module
    from app.main import app

    orchestrator = build_orchestrator(tmp_path).orchestrator
    monkeypatch.setattr(chat_module, "get_orchestrator", lambda: orchestrator)
    client = TestClient(app)

    health = client.get("/api/health").json()
    assert health["status"] == "ok" and "llm_configured" in health

    first = client.post("/api/chat", json={"message": "午饭 25"}).json()
    assert first["intent"] == "record_expense" and first["confirm_required"] is True
    assert first["transaction_preview"][0]["amount"] == 25

    confirmed = client.post(
        "/api/chat/confirm",
        json={"session_id": first["session_id"], "actions": first["pending_actions"]},
    ).json()
    assert confirmed["created"] == 1 and confirmed["failed"] == 0

    stats = client.post(
        "/api/chat", json={"session_id": first["session_id"], "message": "这个月餐饮花了多少"}
    ).json()
    assert stats["intent"] == "query_stats" and "25.00" in stats["reply"]

    invalid = client.post("/api/chat", json={"message": ""})
    assert invalid.status_code == 422 and invalid.json()["code"] == "VALIDATION_ERROR"

    cleared = client.delete(f"/api/chat/session/{first['session_id']}").json()
    assert cleared["cleared"] is True



def test_live_evaluation(request: pytest.FixtureRequest, tmp_path: Path) -> None:
    """真实模型评测：仅在 --live 且已配置 Key 时执行，并输出通过率报告。"""
    if not request.config.getoption("--live"):
        pytest.skip("使用 --live 才执行真实模型评测")
    settings = get_settings()
    if not settings.llm_configured:
        pytest.skip("未配置 LLM_API_KEY，跳过真实模型评测")

    agent = build_orchestrator(tmp_path, llm=LLMClient(settings))
    results: list[dict[str, Any]] = []
    for case in CASES:
        response = agent.chat(f"live-{case['id']}", case["input"])
        actual = response.intent.value
        results.append(
            {
                "id": case["id"],
                "input": case["input"],
                "expected": case["expected_intent"],
                "actual": actual,
                "reply": response.reply,
                "note": case.get("notes", ""),
                "pass": actual == case["expected_intent"],
            }
        )

    passed = sum(1 for item in results if item["pass"])
    rate = passed / len(results)
    report_lines = [
        "# Agent 评测报告（真实模型）",
        "",
        f"- 模型：{settings.llm_model}",
        f"- 用例数：{len(results)}",
        f"- 意图通过率：{passed}/{len(results)}（{rate:.1%}）",
        "",
        "| 用例 | 输入 | 期望意图 | 实际意图 | 结果 |",
        "| --- | --- | --- | --- | --- |",
    ]
    report_lines += [
        f"| {item['id']} | {item['input']} | {item['expected']} | {item['actual']} | {'通过' if item['pass'] else '失败'} |"
        for item in results
    ]
    report_lines += ["", "## 失败归因", ""]
    failed_items = [item for item in results if not item["pass"]]
    if failed_items:
        report_lines += [
            f"- {item['id']}（{item['input']}）：期望 {item['expected']}，实际 {item['actual']}；"
            f"归因参考：{item['note'] or '检查意图路由与槽位抽取'}"
            for item in failed_items
        ]
    else:
        report_lines.append("- 无失败用例。")
    (Path(__file__).parent / "live_report.md").write_text("\n".join(report_lines), encoding="utf-8")
    assert rate >= 0.5, f"真实模型意图通过率过低：{rate:.1%}"
