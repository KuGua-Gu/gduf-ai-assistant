"""账单查询、修改与删除接口。"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.agent.schemas import TransactionFilter
from app.api.business_deps import get_transaction_service
from app.api.business_schemas import (
    DeleteTransactionResponse,
    TransactionListResponse,
    TransactionPatchRequest,
    TransactionResponse,
)
from app.api.errors import BusinessAPIError
from app.services.contracts import TransactionService

router = APIRouter(prefix="/api/transactions", tags=["transactions"])
ServiceDependency = Annotated[TransactionService, Depends(get_transaction_service)]


@router.get("", response_model=TransactionListResponse, summary="查询账单")
def list_transactions(
    service: ServiceDependency,
    start_date: date | None = None,
    end_date: date | None = None,
    category: str | None = None,
    keyword: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> TransactionListResponse:
    """按日期、类别、关键词查询账单列表。"""
    if start_date and end_date and start_date > end_date:
        raise BusinessAPIError(422, "VALIDATION_ERROR", "开始日期不能晚于结束日期。")
    try:
        rows = service.query_transactions(
            TransactionFilter(
                start_date=start_date,
                end_date=end_date,
                category=category,
                keyword=keyword,
                limit=limit,
            )
        )
    except ValueError as exc:
        raise BusinessAPIError(422, "VALIDATION_ERROR", str(exc)) from exc
    items = [TransactionResponse.model_validate(row) for row in rows]
    return TransactionListResponse(items=items, count=len(items))


@router.patch("/{transaction_id}", response_model=TransactionResponse, summary="修改账单")
def update_transaction(
    transaction_id: int,
    payload: TransactionPatchRequest,
    service: ServiceDependency,
) -> TransactionResponse:
    """修改账单的金额、类别、商户、日期或备注。"""
    try:
        updated = service.update_transaction(transaction_id, payload.to_patch())
    except ValueError as exc:
        raise BusinessAPIError(422, "VALIDATION_ERROR", str(exc)) from exc
    if updated is None:
        raise BusinessAPIError(404, "TRANSACTION_NOT_FOUND", "没有找到这笔账单。")
    return TransactionResponse.model_validate(updated)


@router.delete(
    "/{transaction_id}",
    response_model=DeleteTransactionResponse,
    summary="删除账单",
)
def delete_transaction(
    transaction_id: int,
    service: ServiceDependency,
) -> DeleteTransactionResponse:
    """删除指定账单。"""
    if not service.delete_transaction(transaction_id):
        raise BusinessAPIError(404, "TRANSACTION_NOT_FOUND", "没有找到这笔账单。")
    return DeleteTransactionResponse(deleted=True)
