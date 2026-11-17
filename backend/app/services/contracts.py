"""业务层契约（成员 2 按此实现；Agent 只依赖协议，不直接写业务 SQL）。

实现约定：
- ``create_transactions`` 返回每笔记账的落库结果，字段至少包含 ``id``、``amount``、``category``；
- ``get_stats`` 返回 ``{"start","end","group_by","total","items":[{"key","amount","count"}]}``；
- ``set_budget`` 的 ``scope`` 为 ``"total"``（总额）或类别名，``month`` 为 ``YYYY-MM``；
- ``get_budget_status`` 返回
  ``{"month","total_budget","total_spent","items":[{"scope","budget","spent","usage","status"}]}``，
  ``status`` 取值 ``normal | warning | exceeded``。
"""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol, Sequence, runtime_checkable

from app.agent.schemas import OcrResult, TransactionDraft, TransactionFilter


@runtime_checkable
class TransactionService(Protocol):
    """记账业务服务协议。"""

    def create_transactions(
        self, drafts: Sequence[TransactionDraft], session_id: str | None = None
    ) -> list[dict[str, Any]]: ...

    def update_transaction(self, transaction_id: int, patch: dict[str, Any]) -> dict[str, Any] | None: ...

    def delete_transaction(self, transaction_id: int) -> bool: ...

    def query_transactions(self, filters: TransactionFilter) -> list[dict[str, Any]]: ...

    def get_stats(
        self,
        start: date,
        end: date,
        group_by: str = "category",
        category: str | None = None,
    ) -> dict[str, Any]: ...

    def set_budget(self, scope: str, amount: float, month: str) -> dict[str, Any]: ...

    def get_budget_status(self, month: str) -> dict[str, Any]: ...


@runtime_checkable
class OcrService(Protocol):
    """小票识别服务协议（成员 4 实现）。"""

    def recognize(self, image_id: str) -> OcrResult: ...
