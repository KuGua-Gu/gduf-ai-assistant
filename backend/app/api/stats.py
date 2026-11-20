"""消费统计接口。"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends

from app.agent.categories import today_in
from app.api.business_deps import get_transaction_service
from app.api.business_schemas import StatsResponse
from app.api.errors import BusinessAPIError
from app.config import get_settings
from app.services.contracts import TransactionService

router = APIRouter(prefix="/api/stats", tags=["stats"])
ServiceDependency = Annotated[TransactionService, Depends(get_transaction_service)]


@router.get("", response_model=StatsResponse, summary="查询消费统计")
def get_stats(
    service: ServiceDependency,
    start_date: date | None = None,
    end_date: date | None = None,
    group_by: Literal["category", "day", "month"] = "category",
    category: str | None = None,
) -> StatsResponse:
    """按类别、日期或月份返回消费统计。"""
    today = today_in(get_settings().timezone)
    start = start_date or today.replace(day=1)
    end = end_date or today
    if start > end:
        raise BusinessAPIError(422, "VALIDATION_ERROR", "开始日期不能晚于结束日期。")
    try:
        result = service.get_stats(start, end, group_by, category)
    except ValueError as exc:
        raise BusinessAPIError(422, "VALIDATION_ERROR", str(exc)) from exc
    return StatsResponse.model_validate(result)
