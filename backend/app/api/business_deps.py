"""业务 REST 接口依赖装配。"""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.services.contracts import TransactionService
from app.services.transaction_service import SqliteTransactionService


@lru_cache
def get_transaction_service() -> TransactionService:
    """返回进程内复用的 SQLite 业务服务。"""
    return SqliteTransactionService(get_settings().resolved_db_path)
