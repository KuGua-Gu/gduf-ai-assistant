"""成员 2 的 SQLite 业务服务单元测试。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.agent.schemas import TransactionDraft, TransactionFilter, TransactionSource
from app.services.transaction_service import SqliteTransactionService


@pytest.fixture
def service(tmp_path: Path):
    """创建使用独立临时数据库的服务实例。"""
    instance = SqliteTransactionService(tmp_path / "transactions.db")
    yield instance
    instance._engine.dispose()


def draft(
    amount: float,
    category: str,
    occurred_at: date,
    merchant: str = "",
    note: str = "",
    source: TransactionSource = TransactionSource.TEXT,
) -> TransactionDraft:
    """构造测试账单草稿。"""
    return TransactionDraft(
        amount=amount,
        category=category,
        occurred_at=occurred_at,
        merchant=merchant,
        note=note,
        source=source,
    )


def test_create_and_persist_after_reopen(tmp_path: Path) -> None:
    """账单写入后应在新服务实例中继续存在。"""
    db_path = tmp_path / "persistent.db"
    first = SqliteTransactionService(db_path)
    created = first.create_transactions(
        [
            draft(
                25.5,
                "餐饮",
                date(2026, 11, 18),
                merchant="沙县小吃",
                note="午饭",
                source=TransactionSource.OCR,
            )
        ],
        session_id="session-1",
    )
    first._engine.dispose()

    second = SqliteTransactionService(db_path)
    rows = second.query_transactions(TransactionFilter())
    second._engine.dispose()

    assert len(created) == 1
    assert created[0]["id"] == rows[0]["id"]
    assert rows[0]["amount"] == 25.5
    assert rows[0]["category"] == "餐饮"
    assert rows[0]["merchant"] == "沙县小吃"
    assert rows[0]["occurred_at"] == date(2026, 11, 18)
    assert rows[0]["note"] == "午饭"
    assert rows[0]["source"] == "ocr"


def test_batch_create_is_atomic(service: SqliteTransactionService) -> None:
    """批量创建中任意一条非法时，整批都不应写入。"""
    with pytest.raises(ValueError, match="金额必须大于 0"):
        service.create_transactions(
            [
                draft(10.0, "餐饮", date(2026, 11, 18)),
                draft(0.0, "交通", date(2026, 11, 18)),
            ]
        )

    assert service.query_transactions(TransactionFilter()) == []


def test_query_filters_dates_keywords_and_limit(service: SqliteTransactionService) -> None:
    """查询应使用闭区间，并支持类别、关键词、排序和数量限制。"""
    service.create_transactions(
        [
            draft(10.0, "餐饮", date(2026, 10, 31), merchant="早餐店"),
            draft(20.0, "交通", date(2026, 11, 1), merchant="地铁"),
            draft(30.0, "餐饮", date(2026, 11, 30), merchant="晚餐店"),
            draft(40.0, "购物", date(2026, 12, 1), merchant="超市"),
        ]
    )

    november = service.query_transactions(
        TransactionFilter(start_date=date(2026, 11, 1), end_date=date(2026, 11, 30))
    )
    assert [row["occurred_at"] for row in november] == [
        date(2026, 11, 30),
        date(2026, 11, 1),
    ]

    food = service.query_transactions(
        TransactionFilter(
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 30),
            category="餐饮",
        )
    )
    assert len(food) == 1
    assert food[0]["amount"] == 30.0

    keyword = service.query_transactions(TransactionFilter(keyword="晚餐"))
    assert len(keyword) == 1
    assert keyword[0]["merchant"] == "晚餐店"

    limited = service.query_transactions(TransactionFilter(limit=1))
    assert len(limited) == 1
    assert limited[0]["occurred_at"] == date(2026, 12, 1)


def test_stats_grouping_and_money_precision(service: SqliteTransactionService) -> None:
    """统计应按准确金额分组，避免浮点累加误差。"""
    service.create_transactions(
        [
            draft(0.1, "餐饮", date(2026, 11, 1)),
            draft(0.2, "餐饮", date(2026, 11, 1)),
            draft(10.01, "交通", date(2026, 11, 2)),
            draft(5.0, "餐饮", date(2026, 10, 31)),
        ]
    )

    by_category = service.get_stats(
        date(2026, 11, 1),
        date(2026, 11, 30),
        group_by="category",
    )
    assert by_category["total"] == pytest.approx(10.31)
    assert by_category["items"][0] == {
        "key": "交通",
        "amount": pytest.approx(10.01),
        "count": 1,
    }
    assert by_category["items"][1]["key"] == "餐饮"
    assert by_category["items"][1]["amount"] == pytest.approx(0.3)
    assert by_category["items"][1]["count"] == 2

    by_day = service.get_stats(
        date(2026, 11, 1),
        date(2026, 11, 30),
        group_by="day",
    )
    assert [item["key"] for item in by_day["items"]] == ["2026-11-02", "2026-11-01"]

    by_month = service.get_stats(
        date(2026, 10, 1),
        date(2026, 11, 30),
        group_by="month",
    )
    assert by_month["total"] == pytest.approx(15.31)
    assert [item["key"] for item in by_month["items"]] == ["2026-11", "2026-10"]

    food_only = service.get_stats(
        date(2026, 10, 1),
        date(2026, 11, 30),
        category="餐饮",
    )
    assert food_only["total"] == pytest.approx(5.3)
    assert len(food_only["items"]) == 1


def test_update_and_delete_transactions(service: SqliteTransactionService) -> None:
    """更新只处理白名单字段，删除结果应可判断。"""
    created = service.create_transactions(
        [draft(10.0, "餐饮", date(2026, 11, 1), merchant="原商户")]
    )[0]

    updated = service.update_transaction(
        created["id"],
        {
            "amount": "30.25",
            "category": "交通",
            "merchant": "地铁",
            "occurred_at": "2026-11-20",
            "note": "通勤",
            "source": "manual",
        },
    )
    assert updated is not None
    assert updated["amount"] == 30.25
    assert updated["category"] == "交通"
    assert updated["merchant"] == "地铁"
    assert updated["occurred_at"] == date(2026, 11, 20)
    assert updated["note"] == "通勤"
    assert updated["source"] == "text"

    assert service.update_transaction(9999, {"amount": 1}) is None
    assert service.delete_transaction(created["id"]) is True
    assert service.delete_transaction(created["id"]) is False


def test_budget_upsert_and_status_thresholds(service: SqliteTransactionService) -> None:
    """预算应按月份和范围覆盖，并返回正常、警告、超支状态。"""
    service.create_transactions(
        [
            draft(80.0, "餐饮", date(2026, 11, 5)),
            draft(20.0, "交通", date(2026, 11, 6)),
        ]
    )
    service.set_budget("total", 100.0, "2026-11")
    service.set_budget("餐饮", 100.0, "2026-11")
    service.set_budget("交通", 100.0, "2026-11")

    at_thresholds = service.get_budget_status("2026-11")
    items = {item["scope"]: item for item in at_thresholds["items"]}
    assert at_thresholds["total_spent"] == 100.0
    assert items["total"]["status"] == "warning"
    assert items["餐饮"]["usage"] == 0.8
    assert items["餐饮"]["status"] == "warning"
    assert items["交通"]["usage"] == 0.2
    assert items["交通"]["status"] == "normal"

    service.set_budget("total", 50.0, "2026-11")
    exceeded = service.get_budget_status("2026-11")
    total_item = next(item for item in exceeded["items"] if item["scope"] == "total")
    assert exceeded["total_budget"] == 50.0
    assert total_item["usage"] == 2.0
    assert total_item["status"] == "exceeded"

    with service._engine.connect() as conn:
        count = conn.exec_driver_sql(
            "SELECT COUNT(*) FROM budgets WHERE month = ? AND scope = ?",
            ("2026-11", "total"),
        ).scalar_one()
    assert count == 1


def test_budget_month_boundaries(service: SqliteTransactionService) -> None:
    """预算统计应包含当月首尾日期，并排除相邻月份。"""
    service.create_transactions(
        [
            draft(1.0, "餐饮", date(2026, 10, 31)),
            draft(2.0, "餐饮", date(2026, 11, 1)),
            draft(3.0, "餐饮", date(2026, 11, 30)),
            draft(4.0, "餐饮", date(2026, 12, 1)),
        ]
    )
    service.set_budget("total", 100.0, "2026-11")

    status = service.get_budget_status("2026-11")
    assert status["total_spent"] == 5.0
    assert status["items"][0]["spent"] == 5.0


def test_invalid_service_arguments_are_rejected(service: SqliteTransactionService) -> None:
    """非法金额、月份、日期范围和分组方式不应写入或返回错误数据。"""
    with pytest.raises(ValueError, match="金额必须大于 0"):
        service.set_budget("total", 0, "2026-11")
    with pytest.raises(ValueError, match="YYYY-MM"):
        service.set_budget("total", 100, "2026-13")
    with pytest.raises(ValueError, match="开始日期"):
        service.get_stats(date(2026, 11, 30), date(2026, 11, 1))
    with pytest.raises(ValueError, match="group_by"):
        service.get_stats(
            date(2026, 11, 1),
            date(2026, 11, 30),
            group_by="year",
        )

    created = service.create_transactions(
        [draft(10.0, "餐饮", date(2026, 11, 1))]
    )[0]
    with pytest.raises(ValueError, match="金额必须大于 0"):
        service.update_transaction(created["id"], {"amount": -1})
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        service.update_transaction(created["id"], {"occurred_at": "2026-11-31"})

    unchanged = service.query_transactions(TransactionFilter())
    assert unchanged[0]["amount"] == 10.0
    assert unchanged[0]["occurred_at"] == date(2026, 11, 1)
