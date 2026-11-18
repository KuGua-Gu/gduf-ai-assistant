"""跨成员契约测试：API 与服务实现必须符合 docs/api-contract.md。

设计目标：成员 2 交付 ``SqliteTransactionService`` 后无需改测试，自动对真实实现跑同一组断言。
未交付时对内存桩执行，真实实现用例标记为 skip。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.agent.mock_llm import RuleBasedLLM
from app.agent.memory import MemoryStore
from app.agent.orchestrator import AgentOrchestrator
from app.agent.schemas import Intent, TransactionDraft, TransactionFilter, TransactionSource
from app.api import chat as chat_api
from app.main import create_app
from app.services.contracts import OcrService, TransactionService
from app.services.stubs import InMemoryTransactionService, StubOcrService

DOC_PATH = Path(__file__).resolve().parents[1] / "docs" / "api-contract.md"
DOC_TEXT = DOC_PATH.read_text(encoding="utf-8")

CHAT_RESPONSE_FIELDS = {
    "session_id",
    "reply",
    "intent",
    "pending_actions",
    "transaction_preview",
    "confirm_required",
    "trace_id",
}
CONFIRM_RESPONSE_FIELDS = {"session_id", "created", "failed", "reply", "trace_id"}
HEALTH_FIELDS = {"status", "llm_configured", "llm_model"}
ERROR_FIELDS = {"code", "message", "trace_id"}
TRANSACTION_FIELDS = {"id", "amount", "category", "merchant", "occurred_at", "note", "source"}
STATS_FIELDS = {"start", "end", "group_by", "total", "items"}
BUDGET_STATUS_FIELDS = {"month", "total_budget", "total_spent", "items"}
BUDGET_ITEM_FIELDS = {"scope", "budget", "spent", "usage", "status"}
ERROR_CODES = {
    "VALIDATION_ERROR",
    "LLM_UNAVAILABLE",
    "OUTPUT_FORMAT_ERROR",
    "TOOL_EXECUTION_ERROR",
    "CONTEXT_OVERFLOW",
    "SAFETY_VIOLATION",
    "AGENT_ERROR",
}


def _real_transaction_service_cls() -> type[Any] | None:
    """成员 2 交付后自动发现；导入失败说明尚未实现。"""
    try:
        from app.services.transaction_service import SqliteTransactionService  # type: ignore
    except ImportError:
        return None
    return SqliteTransactionService


@pytest.fixture(params=["stub", "sqlite"])
def transaction_service(request: pytest.FixtureRequest, tmp_path: Path) -> TransactionService:
    if request.param == "stub":
        return InMemoryTransactionService()

    cls = _real_transaction_service_cls()
    if cls is None:
        pytest.skip("成员 2 的 SqliteTransactionService 尚未交付")
    return cls(tmp_path / "contract.db")


def test_transaction_service_contract(transaction_service: TransactionService) -> None:
    """按 docs/api-contract.md 的 Protocol 逐项校验业务实现。"""
    assert isinstance(transaction_service, TransactionService)

    draft = TransactionDraft(
        amount=25.0,
        category="餐饮",
        merchant="沙县小吃",
        occurred_at=date(2026, 11, 18),
        note="午饭",
        source=TransactionSource.TEXT,
    )
    created = transaction_service.create_transactions([draft], session_id="contract-session")
    assert len(created) == 1
    row = created[0]
    assert TRANSACTION_FIELDS <= set(row)
    assert row["amount"] == 25.0
    assert row["category"] == "餐饮"
    transaction_id = row["id"]

    listed = transaction_service.query_transactions(
        TransactionFilter(start_date=date(2026, 11, 1), end_date=date(2026, 11, 30))
    )
    assert any(item["id"] == transaction_id for item in listed)
    for item in listed:
        assert TRANSACTION_FIELDS <= set(item)

    stats = transaction_service.get_stats(date(2026, 11, 1), date(2026, 11, 30))
    assert STATS_FIELDS <= set(stats)
    assert stats["total"] == 25.0
    assert stats["items"]
    for item in stats["items"]:
        assert {"key", "amount", "count"} <= set(item)

    budget = transaction_service.set_budget("total", 1000.0, "2026-11")
    assert {"month", "scope", "amount"} <= set(budget)
    assert budget["amount"] == 1000.0

    status = transaction_service.get_budget_status("2026-11")
    assert BUDGET_STATUS_FIELDS <= set(status)
    assert status["total_spent"] == 25.0
    assert status["items"]
    for item in status["items"]:
        assert BUDGET_ITEM_FIELDS <= set(item)
        assert item["status"] in {"normal", "warning", "exceeded"}

    updated = transaction_service.update_transaction(transaction_id, {"merchant": "兰州拉面"})
    assert updated is not None
    assert updated["merchant"] == "兰州拉面"

    assert transaction_service.delete_transaction(transaction_id) is True
    assert transaction_service.delete_transaction(transaction_id) is False


def test_ocr_service_contract() -> None:
    """OCR 协议与返回结构；成员 4 接入真实服务后可在此追加参数化。"""
    service = StubOcrService()
    assert isinstance(service, OcrService)
    result = service.recognize("sample-image")
    assert 0 <= result.confidence <= 1
    assert isinstance(result.merchant, str)
    assert isinstance(result.raw, dict)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    orchestrator = AgentOrchestrator(
        llm=RuleBasedLLM(),
        transactions=InMemoryTransactionService(),
        ocr=StubOcrService(),
        memory=MemoryStore(tmp_path / "contract-agent.db", window=8),
    )
    monkeypatch.setattr(chat_api, "get_orchestrator", lambda: orchestrator)
    return TestClient(create_app())


def test_health_contract(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert set(response.json()) == HEALTH_FIELDS


def test_chat_contract(client: TestClient) -> None:
    response = client.post("/api/chat", json={"message": "午饭 25"})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == CHAT_RESPONSE_FIELDS
    assert body["intent"] in {intent.value for intent in Intent}
    assert body["pending_actions"]
    assert body["confirm_required"] is True

    action = body["pending_actions"][0]
    assert {"action", "draft", "transaction_id", "patch"} <= set(action)
    assert {
        "amount",
        "category",
        "merchant",
        "occurred_at",
        "note",
        "source",
        "confidence",
        "needs_review",
    } <= set(action["draft"])
    if body["transaction_preview"]:
        assert {
            "amount",
            "category",
            "merchant",
            "occurred_at",
            "note",
            "source",
            "needs_review",
        } <= set(body["transaction_preview"][0])


def test_confirm_contract(client: TestClient) -> None:
    chat_body = client.post("/api/chat", json={"message": "午饭 25"}).json()
    response = client.post(
        "/api/chat/confirm",
        json={"session_id": chat_body["session_id"], "actions": chat_body["pending_actions"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == CONFIRM_RESPONSE_FIELDS
    assert body["created"] >= 1


def test_validation_error_contract(client: TestClient) -> None:
    response = client.post("/api/chat", json={"message": ""})
    assert response.status_code == 422
    body = response.json()
    assert set(body) == ERROR_FIELDS
    assert body["code"] == "VALIDATION_ERROR"


def test_contract_doc_lists_all_intents_and_error_codes() -> None:
    for intent in Intent:
        assert f"`{intent.value}`" in DOC_TEXT, f"api-contract.md 缺少意图 {intent.value}"
    for code in ERROR_CODES:
        assert f"`{code}`" in DOC_TEXT, f"api-contract.md 缺少错误码 {code}"


def test_contract_doc_lists_documented_fields() -> None:
    fields = (
        CHAT_RESPONSE_FIELDS
        | CONFIRM_RESPONSE_FIELDS
        | HEALTH_FIELDS
        | TRANSACTION_FIELDS
        | STATS_FIELDS
        | BUDGET_STATUS_FIELDS
        | BUDGET_ITEM_FIELDS
    )
    for field in fields:
        assert (
            f"`{field}`" in DOC_TEXT or f'"{field}"' in DOC_TEXT
        ), f"api-contract.md 缺少字段 {field}"
