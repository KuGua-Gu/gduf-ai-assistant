"""示例账单 CSV 导入器测试。"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from app.agent.schemas import TransactionFilter
from app.db.init_db import DEFAULT_CSV_PATH, SEED_SESSION_PREFIX, import_seed_data
from app.services.transaction_service import SqliteTransactionService


def test_demo_seed_import_is_idempotent(tmp_path: Path) -> None:
    """重复运行导入器不应新增重复账单。"""
    db_path = tmp_path / "demo.db"
    anchor = date(2026, 11, 21)

    first = import_seed_data(db_path, DEFAULT_CSV_PATH, anchor)
    second = import_seed_data(db_path, DEFAULT_CSV_PATH, anchor)

    assert first.inserted == 16
    assert first.skipped == 0
    assert first.total == 16
    assert second.inserted == 0
    assert second.skipped == 16
    assert second.total == 16

    service = SqliteTransactionService(db_path)
    try:
        rows = service.query_transactions(TransactionFilter(limit=200))
        assert len(rows) == 16
        assert service.find_by_session_id(f"{SEED_SESSION_PREFIX}demo-001") is not None
    finally:
        service._engine.dispose()


def test_demo_seed_import_remains_idempotent_when_anchor_changes(tmp_path: Path) -> None:
    """seed_key 是幂等键，改变相对日期基准也不会复制已有示例。"""
    db_path = tmp_path / "demo-anchor.db"
    first_anchor = date(2026, 11, 21)
    second_anchor = first_anchor + timedelta(days=1)

    first = import_seed_data(db_path, DEFAULT_CSV_PATH, first_anchor)
    second = import_seed_data(db_path, DEFAULT_CSV_PATH, second_anchor)

    assert first.inserted == 16
    assert second.inserted == 0
    assert second.skipped == 16

    service = SqliteTransactionService(db_path)
    try:
        rows = service.query_transactions(TransactionFilter(limit=200))
        assert len(rows) == 16
        latest = max(row["occurred_at"] for row in rows if row["occurred_at"] is not None)
        earliest = min(row["occurred_at"] for row in rows if row["occurred_at"] is not None)
        assert latest == first_anchor
        assert earliest == first_anchor - timedelta(days=55)
    finally:
        service._engine.dispose()


def test_invalid_seed_csv_is_rejected(tmp_path: Path) -> None:
    """缺字段或重复 seed_key 的 CSV 应在写库前失败。"""
    csv_path = tmp_path / "invalid.csv"
    csv_path.write_text(
        "seed_key,category,amount,merchant,date_offset_days,note,source\n"
        "duplicate,餐饮,10,商户,0,备注,text\n"
        "duplicate,交通,20,商户,-1,备注,text\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="seed_key 重复"):
        import_seed_data(tmp_path / "invalid.db", csv_path, date(2026, 11, 21))
