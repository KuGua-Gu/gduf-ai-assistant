"""依赖装配：把 Agent、业务服务、OCR 服务按配置组装成单例。

业务层与 OCR 服务由其他成员实现；未就绪时自动降级为内存桩，保证 Agent 可独立运行。
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.agent.orchestrator import AgentOrchestrator
from app.config import get_settings
from app.services.contracts import OcrService, TransactionService
from app.services.stubs import InMemoryTransactionService, StubOcrService

logger = logging.getLogger("app.deps")


def _build_transaction_service() -> TransactionService:
    """优先使用成员 2 的 SQLite 实现，未就绪时使用内存桩。"""
    try:
        from app.services.transaction_service import SqliteTransactionService  # type: ignore

        return SqliteTransactionService(get_settings().resolved_db_path)
    except Exception:  # noqa: BLE001 - 导入失败即降级
        logger.warning("未找到 SqliteTransactionService，使用内存桩实现（数据不会持久化）")
        return InMemoryTransactionService()


def _build_ocr_service() -> OcrService:
    """优先使用成员 4 的识别实现，未就绪时使用返回样例小票的桩。"""
    try:
        from app.services.ocr_service import ReceiptOcrService  # type: ignore

        return ReceiptOcrService()
    except Exception:  # noqa: BLE001 - 导入失败即降级
        logger.warning("未找到 ReceiptOcrService，使用 OCR 桩实现")
        return StubOcrService()


@lru_cache
def get_orchestrator() -> AgentOrchestrator:
    settings = get_settings()
    return AgentOrchestrator(
        transactions=_build_transaction_service(),
        ocr=_build_ocr_service(),
        settings=settings,
    )
