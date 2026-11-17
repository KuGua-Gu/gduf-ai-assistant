"""工具层：工具定义、JSON Schema 导出、参数校验与执行。

设计要点：
- Agent 只通过 ToolRegistry 触达业务能力，不直接写 SQL；
- 写操作（create/update/delete）在对话阶段不直接落库，统一转成 PendingAction 等待用户确认；
- 参数校验失败时把结构化错误回填给模型，由模型决定追问还是修正。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from app.agent.categories import normalize_category, today_in
from app.agent.errors import ToolExecutionError
from app.agent.schemas import PendingAction, ToolResult, TransactionDraft, TransactionFilter
from app.services.contracts import OcrService, TransactionService

logger = logging.getLogger("app.agent.tools")

WriteAction = Literal["create", "update", "delete"]


# ---------- 工具入参模型 ----------


class CreateTransactionsArgs(BaseModel):
    transactions: list[TransactionDraft] = Field(min_length=1, description="待记账的消费条目，可一次多条")


class UpdateTransactionArgs(BaseModel):
    transaction_id: int = Field(ge=1)
    patch: dict[str, Any] = Field(description="需要修改的字段：amount/category/merchant/occurred_at/note")


class DeleteTransactionArgs(BaseModel):
    transaction_id: int = Field(ge=1)


class QueryTransactionsArgs(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    category: str | None = None
    keyword: str | None = None
    limit: int = Field(default=50, ge=1, le=200)


class GetStatsArgs(BaseModel):
    start_date: date | None = Field(default=None, description="统计起始日期，缺省为本月 1 日")
    end_date: date | None = Field(default=None, description="统计结束日期，缺省为今天")
    group_by: Literal["category", "day", "month"] = "category"
    category: str | None = None


class SetBudgetArgs(BaseModel):
    scope: str = Field(description="预算范围：total 表示总额，或具体类别名（餐饮/交通…）")
    amount: float = Field(gt=0, description="预算金额（元）")
    month: str | None = Field(default=None, description="YYYY-MM，缺省为本月")


class GetBudgetStatusArgs(BaseModel):
    month: str | None = Field(default=None, description="YYYY-MM，缺省为本月")


class OcrReceiptArgs(BaseModel):
    image_id: str = Field(min_length=1)


# ---------- 工具规格与注册表 ----------


@dataclass
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[[Any], ToolResult]
    write_action: WriteAction | None = None

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.args_model.model_json_schema(),
            },
        }


def _describe_validation_error(exc: ValidationError) -> str:
    parts = []
    for error in exc.errors():
        location = ".".join(str(item) for item in error["loc"])
        parts.append(f"{location}: {error['msg']}")
    return "; ".join(parts) or "参数不合法"


class ToolRegistry:
    """工具注册表：注册、导出 OpenAI Schema、校验并执行。"""

    MAX_ERROR_HINT = 300

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"工具重复注册：{spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def to_openai_tools(self) -> list[dict[str, Any]]:
        return [spec.to_openai_schema() for spec in self._tools.values()]

    def validate(self, name: str, arguments: dict[str, Any]) -> tuple[BaseModel | None, ToolResult | None]:
        """校验参数，返回 (参数字模型, None) 或 (None, 失败结果)。"""
        spec = self._tools.get(name)
        if spec is None:
            return None, ToolResult.failure(f"未知工具：{name}")
        try:
            return spec.args_model.model_validate(arguments or {}), None
        except ValidationError as exc:
            return None, ToolResult.failure(f"参数校验失败：{_describe_validation_error(exc)}")

    def execute(self, name: str, arguments: dict[str, Any], trace_id: str = "") -> ToolResult:
        """校验后执行工具，任何异常都转成结构化结果而不是抛给调用方。"""
        started_at = time.perf_counter()
        args, failure = self.validate(name, arguments)
        if failure is not None:
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            logger.info(
                "trace=%s tool=%s elapsed_ms=%.1f ok=%s error=%s",
                trace_id or "-",
                name,
                elapsed_ms,
                False,
                (failure.error or "")[: self.MAX_ERROR_HINT],
            )
            return failure
        spec = self._tools[name]
        try:
            result = spec.handler(args)
        except ToolExecutionError as exc:
            result = ToolResult.failure(exc.detail or exc.user_message)
        except Exception as exc:  # noqa: BLE001 - 工具边界统一兜底
            result = ToolResult.failure(f"工具执行异常：{exc.__class__.__name__}: {exc}")
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        if result.ok:
            logger.info(
                "trace=%s tool=%s elapsed_ms=%.1f ok=%s",
                trace_id or "-",
                name,
                elapsed_ms,
                True,
            )
        else:
            logger.info(
                "trace=%s tool=%s elapsed_ms=%.1f ok=%s error=%s",
                trace_id or "-",
                name,
                elapsed_ms,
                False,
                (result.error or "")[: self.MAX_ERROR_HINT],
            )
        return result

    def to_pending_actions(
        self, name: str, arguments: dict[str, Any], trace_id: str = ""
    ) -> tuple[list[PendingAction], list[str]]:
        """把写操作转成待确认动作；返回 (动作列表, 仍缺失的字段)。"""
        started_at = time.perf_counter()
        args, failure = self.validate(name, arguments)
        if failure is not None:
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            logger.info(
                "trace=%s tool=%s elapsed_ms=%.1f ok=%s actions=%d error=%s",
                trace_id or "-",
                name,
                elapsed_ms,
                False,
                0,
                (failure.error or "")[: self.MAX_ERROR_HINT],
            )
            return [], [failure.error or "参数不合法"]

        spec = self._tools[name]
        actions: list[PendingAction] = []
        missing: list[str] = []
        if spec.write_action == "create":
            assert isinstance(args, CreateTransactionsArgs)
            for draft in args.transactions:
                draft.category = normalize_category(draft.category)
                for field_name in draft.missing_fields():
                    if field_name not in missing:
                        missing.append(field_name)
                actions.append(PendingAction(action="create", draft=draft))
        elif spec.write_action == "update":
            assert isinstance(args, UpdateTransactionArgs)
            actions = [PendingAction(action="update", transaction_id=args.transaction_id, patch=args.patch)]
        elif spec.write_action == "delete":
            assert isinstance(args, DeleteTransactionArgs)
            actions = [PendingAction(action="delete", transaction_id=args.transaction_id)]

        elapsed_ms = (time.perf_counter() - started_at) * 1000
        logger.info(
            "trace=%s tool=%s elapsed_ms=%.1f ok=%s actions=%d",
            trace_id or "-",
            name,
            elapsed_ms,
            True,
            len(actions),
        )
        return actions, missing


def build_default_registry(
    transactions: TransactionService,
    ocr: OcrService | None = None,
    timezone: str = "Asia/Shanghai",
) -> ToolRegistry:
    """注册 7 个核心工具（OCR 可用时追加第 8 个）。"""

    registry = ToolRegistry()
    today = lambda: today_in(timezone)  # noqa: E731

    def create_handler(args: CreateTransactionsArgs) -> ToolResult:
        created = transactions.create_transactions(args.transactions)
        return ToolResult.success({"created": created})

    def update_handler(args: UpdateTransactionArgs) -> ToolResult:
        updated = transactions.update_transaction(args.transaction_id, args.patch)
        if updated is None:
            return ToolResult.failure(f"没有找到 id={args.transaction_id} 的账单")
        return ToolResult.success({"updated": updated})

    def delete_handler(args: DeleteTransactionArgs) -> ToolResult:
        if not transactions.delete_transaction(args.transaction_id):
            return ToolResult.failure(f"没有找到 id={args.transaction_id} 的账单")
        return ToolResult.success({"deleted_id": args.transaction_id})

    def query_handler(args: QueryTransactionsArgs) -> ToolResult:
        filters = TransactionFilter(
            start_date=args.start_date,
            end_date=args.end_date,
            category=normalize_category(args.category),
            keyword=args.keyword,
            limit=args.limit,
        )
        rows = transactions.query_transactions(filters)
        return ToolResult.success({"count": len(rows), "items": rows})

    def stats_handler(args: GetStatsArgs) -> ToolResult:
        start = args.start_date or today().replace(day=1)
        end = args.end_date or today()
        if start > end:
            return ToolResult.failure("start_date 不能晚于 end_date")
        stats = transactions.get_stats(start, end, args.group_by, normalize_category(args.category))
        return ToolResult.success(stats)

    def set_budget_handler(args: SetBudgetArgs) -> ToolResult:
        month = args.month or today().strftime("%Y-%m")
        scope = "total" if args.scope in {"total", "总额", "总预算"} else (normalize_category(args.scope) or "total")
        return ToolResult.success(transactions.set_budget(scope, args.amount, month))

    def budget_status_handler(args: GetBudgetStatusArgs) -> ToolResult:
        month = args.month or today().strftime("%Y-%m")
        return ToolResult.success(transactions.get_budget_status(month))

    def ocr_handler(args: OcrReceiptArgs) -> ToolResult:
        assert ocr is not None
        result = ocr.recognize(args.image_id)
        return ToolResult.success(result.model_dump(mode="json"))

    registry.register(
        ToolSpec(
            name="create_transactions",
            description="新增记账条目（写操作，需用户确认后才落库）。一条消息包含多笔消费时放在 transactions 数组里。",
            args_model=CreateTransactionsArgs,
            handler=create_handler,
            write_action="create",
        )
    )
    registry.register(
        ToolSpec(
            name="update_transaction",
            description="修改已有账单的金额/类别/商户/日期/备注（写操作，需用户确认）。",
            args_model=UpdateTransactionArgs,
            handler=update_handler,
            write_action="update",
        )
    )
    registry.register(
        ToolSpec(
            name="delete_transaction",
            description="删除一笔账单（写操作，需用户确认）。",
            args_model=DeleteTransactionArgs,
            handler=delete_handler,
            write_action="delete",
        )
    )
    registry.register(
        ToolSpec(
            name="query_transactions",
            description="按日期范围、类别、关键词查询账单明细，用于「我上周买了什么」这类问题。",
            args_model=QueryTransactionsArgs,
            handler=query_handler,
        )
    )
    registry.register(
        ToolSpec(
            name="get_stats",
            description="按类别/天/月统计一段时间内的消费金额，用于「上个月吃饭花了多少」「哪类花得最多」。",
            args_model=GetStatsArgs,
            handler=stats_handler,
        )
    )
    registry.register(
        ToolSpec(
            name="set_budget",
            description="设置月度预算，scope 为 total 或具体类别。",
            args_model=SetBudgetArgs,
            handler=set_budget_handler,
            write_action=None,
        )
    )
    registry.register(
        ToolSpec(
            name="get_budget_status",
            description="查询某月预算使用情况，返回是否接近或超出预算。",
            args_model=GetBudgetStatusArgs,
            handler=budget_status_handler,
        )
    )
    if ocr is not None:
        registry.register(
            ToolSpec(
                name="ocr_receipt",
                description="识别小票/支付截图，返回金额、商户、日期与置信度。",
                args_model=OcrReceiptArgs,
                handler=ocr_handler,
            )
        )
    return registry
