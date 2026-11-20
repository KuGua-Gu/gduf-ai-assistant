"""成员 2 的业务 REST 接口测试。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agent.memory import MemoryStore
from app.agent.mock_llm import RuleBasedLLM
from app.agent.orchestrator import AgentOrchestrator
from app.agent.schemas import TransactionDraft
from app.api import chat as chat_api
from app.api.business_deps import get_transaction_service
from app.main import create_app
from app.services.stubs import StubOcrService
from app.services.transaction_service import SqliteTransactionService


@pytest.fixture
def service(tmp_path: Path):
    """创建接口测试使用的临时 SQLite 服务。"""
    instance = SqliteTransactionService(tmp_path / "business-api.db")
    yield instance
    instance._engine.dispose()


@pytest.fixture
def client(service: SqliteTransactionService):
    """创建覆盖业务服务依赖的 FastAPI 测试客户端。"""
    app = create_app()
    app.dependency_overrides[get_transaction_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _draft(
    amount: float,
    category: str,
    occurred_at: date,
    merchant: str = "",
    note: str = "",
) -> TransactionDraft:
    return TransactionDraft(
        amount=amount,
        category=category,
        merchant=merchant,
        occurred_at=occurred_at,
        note=note,
    )


def test_list_transactions_filters_and_validation(client: TestClient, service: SqliteTransactionService) -> None:
    """账单列表接口应支持筛选并返回稳定结构。"""
    service.create_transactions(
        [
            _draft(10.0, "餐饮", date(2026, 11, 1), merchant="早餐店"),
            _draft(20.0, "交通", date(2026, 11, 2), merchant="地铁"),
            _draft(30.0, "餐饮", date(2026, 11, 3), merchant="晚餐店", note="同事聚餐"),
        ]
    )

    response = client.get("/api/transactions")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 3
    assert [item["occurred_at"] for item in body["items"]] == [
        "2026-11-03",
        "2026-11-02",
        "2026-11-01",
    ]

    filtered = client.get(
        "/api/transactions",
        params={
            "start_date": "2026-11-02",
            "end_date": "2026-11-03",
            "category": "交通",
        },
    )
    assert filtered.status_code == 200
    assert filtered.json()["count"] == 1
    assert filtered.json()["items"][0]["merchant"] == "地铁"

    keyword = client.get("/api/transactions", params={"keyword": "聚餐", "limit": 1})
    assert keyword.status_code == 200
    assert keyword.json()["count"] == 1

    invalid_range = client.get(
        "/api/transactions",
        params={"start_date": "2026-11-30", "end_date": "2026-11-01"},
    )
    assert invalid_range.status_code == 422
    assert invalid_range.json()["code"] == "VALIDATION_ERROR"
    assert set(invalid_range.json()) == {"code", "message", "trace_id"}

    invalid_limit = client.get("/api/transactions", params={"limit": 0})
    assert invalid_limit.status_code == 422
    assert invalid_limit.json()["code"] == "VALIDATION_ERROR"


def test_update_transaction_and_not_found(client: TestClient, service: SqliteTransactionService) -> None:
    """账单修改接口应只更新提供字段，并正确处理 404 和 422。"""
    created = service.create_transactions(
        [_draft(10.0, "餐饮", date(2026, 11, 1), merchant="原商户")]
    )[0]

    response = client.patch(
        f"/api/transactions/{created['id']}",
        json={
            "amount": 30.25,
            "category": "交通",
            "merchant": "地铁",
            "occurred_at": "2026-11-20",
            "note": "通勤",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["amount"] == 30.25
    assert body["category"] == "交通"
    assert body["occurred_at"] == "2026-11-20"
    assert body["source"] == "text"

    empty_patch = client.patch(f"/api/transactions/{created['id']}", json={})
    assert empty_patch.status_code == 422
    assert empty_patch.json()["code"] == "VALIDATION_ERROR"

    invalid_amount = client.patch(f"/api/transactions/{created['id']}", json={"amount": -1})
    assert invalid_amount.status_code == 422

    missing = client.patch("/api/transactions/9999", json={"merchant": "不存在"})
    assert missing.status_code == 404
    assert missing.json()["code"] == "TRANSACTION_NOT_FOUND"
    assert set(missing.json()) == {"code", "message", "trace_id"}


def test_delete_transaction(client: TestClient, service: SqliteTransactionService) -> None:
    """删除接口应返回删除结果，重复删除返回 404。"""
    created = service.create_transactions(
        [_draft(10.0, "餐饮", date(2026, 11, 1))]
    )[0]

    response = client.delete(f"/api/transactions/{created['id']}")
    assert response.status_code == 200
    assert response.json() == {"deleted": True}
    assert client.get("/api/transactions").json()["count"] == 0

    repeated = client.delete(f"/api/transactions/{created['id']}")
    assert repeated.status_code == 404
    assert repeated.json()["code"] == "TRANSACTION_NOT_FOUND"


def test_stats_api_grouping_and_validation(client: TestClient, service: SqliteTransactionService) -> None:
    """统计接口应支持三种分组并拒绝非法范围。"""
    service.create_transactions(
        [
            _draft(10.0, "餐饮", date(2026, 11, 1)),
            _draft(20.0, "交通", date(2026, 11, 2)),
            _draft(30.0, "餐饮", date(2026, 11, 2)),
        ]
    )

    by_category = client.get(
        "/api/stats",
        params={"start_date": "2026-11-01", "end_date": "2026-11-30"},
    )
    assert by_category.status_code == 200
    body = by_category.json()
    assert body["total"] == 60.0
    assert body["group_by"] == "category"
    assert body["items"][0] == {"key": "餐饮", "amount": 40.0, "count": 2}

    by_day = client.get(
        "/api/stats",
        params={
            "start_date": "2026-11-01",
            "end_date": "2026-11-30",
            "group_by": "day",
        },
    )
    assert by_day.status_code == 200
    assert [item["key"] for item in by_day.json()["items"]] == ["2026-11-02", "2026-11-01"]

    invalid_range = client.get(
        "/api/stats",
        params={"start_date": "2026-11-30", "end_date": "2026-11-01"},
    )
    assert invalid_range.status_code == 422
    assert invalid_range.json()["code"] == "VALIDATION_ERROR"

    invalid_group = client.get("/api/stats", params={"group_by": "year"})
    assert invalid_group.status_code == 422
    assert invalid_group.json()["code"] == "VALIDATION_ERROR"


def test_budget_api_set_and_query(client: TestClient, service: SqliteTransactionService) -> None:
    """预算接口应支持设置、覆盖和查询状态。"""
    service.create_transactions(
        [
            _draft(80.0, "餐饮", date(2026, 11, 5)),
            _draft(20.0, "交通", date(2026, 11, 6)),
        ]
    )

    created = client.put(
        "/api/budgets",
        json={"month": "2026-11", "scope": "total", "amount": 100},
    )
    assert created.status_code == 200
    assert created.json() == {"month": "2026-11", "scope": "total", "amount": 100.0}

    status = client.get("/api/budgets", params={"month": "2026-11"})
    assert status.status_code == 200
    body = status.json()
    assert body["total_spent"] == 100.0
    assert body["total_budget"] == 100.0
    assert body["items"][0]["status"] == "warning"

    updated = client.put(
        "/api/budgets",
        json={"month": "2026-11", "scope": "total", "amount": 50},
    )
    assert updated.status_code == 200
    exceeded = client.get("/api/budgets", params={"month": "2026-11"})
    assert exceeded.json()["items"][0]["status"] == "exceeded"

    invalid_month = client.get("/api/budgets", params={"month": "2026-13"})
    assert invalid_month.status_code == 422
    assert invalid_month.json()["code"] == "VALIDATION_ERROR"

    invalid_budget = client.put(
        "/api/budgets",
        json={"month": "2026-11", "scope": "total", "amount": 0},
    )
    assert invalid_budget.status_code == 422
    assert invalid_budget.json()["code"] == "VALIDATION_ERROR"


def test_agent_confirm_persists_for_business_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Agent 确认入账后，业务 API 应能读取重启后的 SQLite 数据。"""
    db_path = tmp_path / "agent-business.db"
    first_service = SqliteTransactionService(db_path)
    orchestrator = AgentOrchestrator(
        llm=RuleBasedLLM(),
        transactions=first_service,
        ocr=StubOcrService(),
        memory=MemoryStore(tmp_path / "agent-memory.db", window=8),
    )
    first_app = create_app()
    first_app.dependency_overrides[get_transaction_service] = lambda: first_service
    monkeypatch.setattr(chat_api, "get_orchestrator", lambda: orchestrator)

    with TestClient(first_app) as first_client:
        chat = first_client.post("/api/chat", json={"message": "午饭 25"})
        assert chat.status_code == 200
        payload = chat.json()
        confirmed = first_client.post(
            "/api/chat/confirm",
            json={
                "session_id": payload["session_id"],
                "actions": payload["pending_actions"],
            },
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["created"] == 1
    first_service._engine.dispose()

    second_service = SqliteTransactionService(db_path)
    second_app = create_app()
    second_app.dependency_overrides[get_transaction_service] = lambda: second_service
    with TestClient(second_app) as second_client:
        listed = second_client.get("/api/transactions")
        assert listed.status_code == 200
        body = listed.json()
        assert body["count"] == 1
        assert body["items"][0]["amount"] == 25.0
        assert body["items"][0]["category"] == "餐饮"
    second_service._engine.dispose()
