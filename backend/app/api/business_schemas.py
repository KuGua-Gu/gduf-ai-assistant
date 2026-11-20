"""业务 REST 接口的请求与响应模型。"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class TransactionResponse(BaseModel):
    """账单记录响应。"""

    id: int
    amount: float
    category: str
    merchant: str
    occurred_at: date
    note: str
    source: Literal["text", "ocr", "manual"]


class TransactionListResponse(BaseModel):
    """账单列表响应。"""

    items: list[TransactionResponse]
    count: int


class TransactionPatchRequest(BaseModel):
    """账单局部更新请求，至少提供一个可修改字段。"""

    amount: float | None = Field(default=None, gt=0)
    category: str | None = Field(default=None, max_length=50)
    merchant: str | None = Field(default=None, max_length=200)
    occurred_at: date | None = None
    note: str | None = Field(default=None, max_length=500)

    @field_validator("category")
    @classmethod
    def _category_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("类别不能为空")
        return value.strip() if value is not None else value

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "TransactionPatchRequest":
        if not self.model_fields_set:
            raise ValueError("至少提供一个需要修改的字段")
        return self

    def to_patch(self) -> dict[str, object]:
        """只返回请求中实际提供的字段。"""
        return self.model_dump(exclude_unset=True)


class DeleteTransactionResponse(BaseModel):
    """删除账单响应。"""

    deleted: bool


class StatsItemResponse(BaseModel):
    """单个统计分组。"""

    key: str
    amount: float
    count: int


class StatsResponse(BaseModel):
    """消费统计响应。"""

    start: date
    end: date
    group_by: Literal["category", "day", "month"]
    total: float
    items: list[StatsItemResponse]


class BudgetStatusItemResponse(BaseModel):
    """单项预算使用状态。"""

    scope: str
    budget: float
    spent: float
    usage: float
    status: Literal["normal", "warning", "exceeded"]


class BudgetStatusResponse(BaseModel):
    """月度预算状态响应。"""

    month: str
    total_budget: float | None
    total_spent: float
    items: list[BudgetStatusItemResponse]


class BudgetUpsertRequest(BaseModel):
    """设置月度预算请求。"""

    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    scope: str = Field(min_length=1, max_length=50)
    amount: float = Field(gt=0)

    @field_validator("scope")
    @classmethod
    def _scope_not_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("预算范围不能为空")
        return normalized


class BudgetResponse(BaseModel):
    """预算设置结果。"""

    month: str
    scope: str
    amount: float
