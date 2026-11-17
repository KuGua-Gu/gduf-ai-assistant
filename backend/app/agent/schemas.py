"""Agent 层数据契约：请求/响应、记账草稿、工具结果。"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Intent(str, Enum):
    """对话意图枚举，与前端展示、评测集 expected_intent 保持一致。"""

    RECORD_EXPENSE = "record_expense"
    QUERY_STATS = "query_stats"
    MANAGE_BUDGET = "manage_budget"
    CONFIRM_ACTION = "confirm_action"
    CHITCHAT = "chitchat"
    REFUSE = "refuse"


class TransactionSource(str, Enum):
    TEXT = "text"
    OCR = "ocr"
    MANUAL = "manual"


class TransactionDraft(BaseModel):
    """待确认的记账草稿。字段允许为空，由澄清流程补齐。"""

    amount: float | None = Field(default=None, ge=0, description="金额（元），未知时为 null")
    category: str | None = Field(default=None, description="消费类别，未知时为 null")
    merchant: str = Field(default="", description="商户/场景描述")
    occurred_at: date | None = Field(default=None, description="发生日期，未知时为 null")
    note: str = Field(default="", description="备注，例如「和同事 AA」")
    source: TransactionSource = TransactionSource.TEXT
    confidence: float = Field(default=1.0, ge=0, le=1)
    needs_review: list[str] = Field(default_factory=list, description="需要用户确认/修正的字段")

    def missing_fields(self) -> list[str]:
        """返回仍缺失、必须追问的字段名。"""
        missing: list[str] = []
        if self.amount is None:
            missing.append("amount")
        if self.category is None:
            missing.append("category")
        if self.occurred_at is None:
            missing.append("occurred_at")
        return missing


class TransactionFilter(BaseModel):
    """查账条件，时间范围闭区间。"""

    start_date: date | None = None
    end_date: date | None = None
    category: str | None = None
    keyword: str | None = None
    limit: int = Field(default=50, ge=1, le=200)


class ToolResult(BaseModel):
    """工具执行结果，ok=False 时 error 回填给模型用于自我修正。"""

    ok: bool
    data: Any = None
    error: str | None = None

    @classmethod
    def success(cls, data: Any = None) -> "ToolResult":
        return cls(ok=True, data=data)

    @classmethod
    def failure(cls, error: str) -> "ToolResult":
        return cls(ok=False, error=error)


class PendingAction(BaseModel):
    """待用户确认的动作，前端据此渲染确认卡片。"""

    action: Literal["create", "update", "delete"] = "create"
    draft: TransactionDraft | None = None
    transaction_id: int | None = None
    patch: dict[str, Any] | None = None


class TransactionPreview(BaseModel):
    """确认卡片中的展示字段，与 TransactionDraft 一一对应。"""

    amount: float | None = None
    category: str | None = None
    merchant: str = ""
    occurred_at: date | None = None
    note: str = ""
    source: str = TransactionSource.TEXT.value
    needs_review: list[str] = Field(default_factory=list)


class OcrResult(BaseModel):
    """OCR 服务返回结构（成员 4 按此实现）。"""

    amount: float | None = None
    merchant: str = ""
    occurred_at: date | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    raw: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    session_id: str | None = Field(default=None, description="前端生成的会话 ID，缺省由后端创建")
    message: str = Field(min_length=1, max_length=2000)
    image_id: str | None = Field(default=None, description="已上传小票/截图在 OCR 服务中的 ID")


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    intent: Intent
    pending_actions: list[PendingAction] = Field(default_factory=list)
    transaction_preview: list[TransactionPreview] = Field(default_factory=list)
    confirm_required: bool = False
    trace_id: str


class ConfirmRequest(BaseModel):
    session_id: str
    actions: list[PendingAction] = Field(min_length=1)


class ConfirmResponse(BaseModel):
    session_id: str
    created: int = 0
    failed: int = 0
    reply: str
    trace_id: str


class ErrorResponse(BaseModel):
    code: str
    message: str
    trace_id: str
