"""预算设置与查询接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.agent.categories import today_in
from app.api.business_deps import get_transaction_service
from app.api.business_schemas import BudgetResponse, BudgetStatusResponse, BudgetUpsertRequest
from app.api.errors import BusinessAPIError
from app.config import get_settings
from app.services.contracts import TransactionService

router = APIRouter(prefix="/api/budgets", tags=["budgets"])
ServiceDependency = Annotated[TransactionService, Depends(get_transaction_service)]


@router.get("", response_model=BudgetStatusResponse, summary="查询月度预算状态")
def get_budget_status(
    service: ServiceDependency,
    month: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
) -> BudgetStatusResponse:
    """查询指定月份的预算使用状态，缺省为当前月。"""
    normalized_month = month or today_in(get_settings().timezone).strftime("%Y-%m")
    try:
        result = service.get_budget_status(normalized_month)
    except ValueError as exc:
        raise BusinessAPIError(422, "VALIDATION_ERROR", str(exc)) from exc
    return BudgetStatusResponse.model_validate(result)


@router.put("", response_model=BudgetResponse, summary="设置月度预算")
def set_budget(
    payload: BudgetUpsertRequest,
    service: ServiceDependency,
) -> BudgetResponse:
    """新增或覆盖某月某范围的预算。"""
    try:
        result = service.set_budget(payload.scope, payload.amount, payload.month)
    except ValueError as exc:
        raise BusinessAPIError(422, "VALIDATION_ERROR", str(exc)) from exc
    return BudgetResponse.model_validate(result)
