"""基于 SQLite 的账单与预算业务服务。"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Sequence

from sqlalchemy import create_engine, event, func, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.agent.schemas import TransactionDraft, TransactionFilter
from app.db.models import Base, BudgetModel, TransactionModel

_CENT = Decimal("0.01")
_MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_ALLOWED_PATCH_FIELDS = {"amount", "category", "merchant", "occurred_at", "note"}


def _amount_to_cents(value: Any) -> int:
    """把元金额转换为整数分，拒绝零、负数和非有限值。"""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("金额格式不合法") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError("金额必须大于 0")
    return int((amount.quantize(_CENT, rounding=ROUND_HALF_UP) * 100).to_integral_value())


def _cents_to_amount(cents: int) -> float:
    """把整数分转换为两位小数的元金额。"""
    return float((Decimal(cents) / 100).quantize(_CENT))


def _as_date(value: Any) -> date:
    """把日期对象或 ISO 日期字符串转换为 ``date``。"""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("日期必须为 YYYY-MM-DD 格式") from exc
    raise ValueError("日期格式不合法")


def _validate_month(month: str) -> str:
    """校验 ``YYYY-MM`` 格式并返回规范化字符串。"""
    normalized = str(month).strip()
    if not _MONTH_PATTERN.fullmatch(normalized):
        raise ValueError("月份必须为 YYYY-MM 格式")
    return normalized


def _month_bounds(month: str) -> tuple[date, date]:
    """返回某月的起始日与下月起始日，结束边界为开区间。"""
    normalized = _validate_month(month)
    start = date.fromisoformat(f"{normalized}-01")
    end = date(
        start.year + (1 if start.month == 12 else 0),
        1 if start.month == 12 else start.month + 1,
        1,
    )
    return start, end


def _row_to_dict(row: TransactionModel) -> dict[str, Any]:
    """把账单 ORM 对象转换成 Agent 契约要求的字典。"""
    return {
        "id": row.id,
        "amount": _cents_to_amount(row.amount_cents),
        "category": row.category,
        "merchant": row.merchant,
        "occurred_at": row.occurred_at,
        "note": row.note,
        "source": row.source,
    }


class SqliteTransactionService:
    """SQLite 账单服务，实现 Agent 层的 ``TransactionService`` 协议。"""

    def __init__(self, db_path: str | Path) -> None:
        """创建数据库目录、引擎与业务表。"""
        self._db_path = Path(db_path).expanduser().resolve()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._engine = create_engine(
            f"sqlite+pysqlite:///{self._db_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        self._configure_sqlite(self._engine)
        Base.metadata.create_all(self._engine)

    @staticmethod
    def _configure_sqlite(engine: Engine) -> None:
        """为每个 SQLite 连接设置 WAL、忙等待和外键约束。"""

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection: Any, _connection_record: Any) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.execute("PRAGMA foreign_keys=ON")
            finally:
                cursor.close()

    def create_transactions(
        self,
        drafts: Sequence[TransactionDraft],
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """批量创建账单；任意一条不合法时整批不写入。"""
        if not drafts:
            return []

        rows: list[TransactionModel] = []
        for draft in drafts:
            if draft.amount is None:
                raise ValueError("金额不能为空")
            category = (draft.category or "").strip()
            if not category:
                raise ValueError("类别不能为空")
            if draft.occurred_at is None:
                raise ValueError("日期不能为空")
            rows.append(
                TransactionModel(
                    amount_cents=_amount_to_cents(draft.amount),
                    category=category,
                    merchant=draft.merchant.strip(),
                    occurred_at=_as_date(draft.occurred_at),
                    note=draft.note.strip(),
                    source=draft.source.value,
                    session_id=session_id,
                )
            )

        with Session(self._engine) as session:
            with session.begin():
                session.add_all(rows)
                session.flush()
                result = [_row_to_dict(row) for row in rows]
        return result

    def update_transaction(
        self,
        transaction_id: int,
        patch: dict[str, Any],
    ) -> dict[str, Any] | None:
        """更新账单允许修改的字段；未知字段会被忽略。"""
        updates = {key: value for key, value in patch.items() if key in _ALLOWED_PATCH_FIELDS}
        with Session(self._engine) as session:
            with session.begin():
                row = session.get(TransactionModel, transaction_id)
                if row is None:
                    return None
                if "amount" in updates:
                    row.amount_cents = _amount_to_cents(updates["amount"])
                if "category" in updates:
                    category = str(updates["category"]).strip()
                    if not category:
                        raise ValueError("类别不能为空")
                    row.category = category
                if "merchant" in updates:
                    row.merchant = str(updates["merchant"]).strip()
                if "occurred_at" in updates:
                    row.occurred_at = _as_date(updates["occurred_at"])
                if "note" in updates:
                    row.note = str(updates["note"]).strip()
                session.flush()
                result = _row_to_dict(row)
        return result

    def delete_transaction(self, transaction_id: int) -> bool:
        """删除指定账单，找不到时返回 ``False``。"""
        with Session(self._engine) as session:
            with session.begin():
                row = session.get(TransactionModel, transaction_id)
                if row is None:
                    return False
                session.delete(row)
        return True

    def query_transactions(self, filters: TransactionFilter) -> list[dict[str, Any]]:
        """按闭区间日期、类别和关键词查询账单，按发生日期倒序返回。"""
        statement = select(TransactionModel)
        if filters.start_date is not None:
            statement = statement.where(TransactionModel.occurred_at >= filters.start_date)
        if filters.end_date is not None:
            statement = statement.where(TransactionModel.occurred_at <= filters.end_date)
        if filters.category:
            statement = statement.where(TransactionModel.category == filters.category)
        if filters.keyword:
            keyword = filters.keyword.strip()
            if keyword:
                statement = statement.where(
                    or_(
                        TransactionModel.merchant.contains(keyword, autoescape=True),
                        TransactionModel.note.contains(keyword, autoescape=True),
                    )
                )
        limit = max(1, min(filters.limit, 200))
        statement = statement.order_by(
            TransactionModel.occurred_at.desc(),
            TransactionModel.id.desc(),
        ).limit(limit)

        with Session(self._engine) as session:
            rows = session.scalars(statement).all()
        return [_row_to_dict(row) for row in rows]

    def find_by_session_id(self, session_id: str) -> dict[str, Any] | None:
        """按会话标识查找账单，用于示例数据导入幂等判断。"""
        with Session(self._engine) as session:
            row = session.scalar(
                select(TransactionModel)
                .where(TransactionModel.session_id == session_id)
                .order_by(TransactionModel.id)
                .limit(1)
            )
        return _row_to_dict(row) if row is not None else None

    def get_stats(
        self,
        start: date,
        end: date,
        group_by: str = "category",
        category: str | None = None,
    ) -> dict[str, Any]:
        """按类别、日期或月份聚合闭区间内的账单金额。"""
        if start > end:
            raise ValueError("开始日期不能晚于结束日期")
        if group_by not in {"category", "day", "month"}:
            raise ValueError("group_by 只支持 category、day 或 month")

        if group_by == "day":
            group_column = func.strftime("%Y-%m-%d", TransactionModel.occurred_at)
        elif group_by == "month":
            group_column = func.strftime("%Y-%m", TransactionModel.occurred_at)
        else:
            group_column = TransactionModel.category

        amount_sum = func.sum(TransactionModel.amount_cents)
        statement = (
            select(
                group_column.label("key"),
                amount_sum.label("amount_cents"),
                func.count(TransactionModel.id).label("count"),
            )
            .where(TransactionModel.occurred_at >= start, TransactionModel.occurred_at <= end)
            .group_by(group_column)
            .order_by(amount_sum.desc(), group_column.asc())
        )
        if category:
            statement = statement.where(TransactionModel.category == category)

        with Session(self._engine) as session:
            rows = session.execute(statement).all()

        items = [
            {
                "key": str(row.key),
                "amount": _cents_to_amount(int(row.amount_cents or 0)),
                "count": int(row.count),
            }
            for row in rows
        ]
        total_cents = sum(int(row.amount_cents or 0) for row in rows)
        return {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "group_by": group_by,
            "total": _cents_to_amount(total_cents),
            "items": items,
        }

    def set_budget(self, scope: str, amount: float, month: str) -> dict[str, Any]:
        """新增或覆盖某月某范围的预算。"""
        normalized_month = _validate_month(month)
        normalized_scope = str(scope).strip()
        if not normalized_scope:
            raise ValueError("预算范围不能为空")
        amount_cents = _amount_to_cents(amount)

        with Session(self._engine) as session:
            with session.begin():
                row = session.scalar(
                    select(BudgetModel).where(
                        BudgetModel.month == normalized_month,
                        BudgetModel.scope == normalized_scope,
                    )
                )
                if row is None:
                    row = BudgetModel(
                        month=normalized_month,
                        scope=normalized_scope,
                        amount_cents=amount_cents,
                    )
                    session.add(row)
                else:
                    row.amount_cents = amount_cents
                    row.created_at = datetime.now(timezone.utc)
                session.flush()
                result = {
                    "month": row.month,
                    "scope": row.scope,
                    "amount": _cents_to_amount(row.amount_cents),
                }
        return result

    def get_budget_status(self, month: str) -> dict[str, Any]:
        """返回某月总支出、预算余额比例及状态。"""
        normalized_month = _validate_month(month)
        start, end = _month_bounds(normalized_month)

        with Session(self._engine) as session:
            spending_rows = session.execute(
                select(
                    TransactionModel.category,
                    func.sum(TransactionModel.amount_cents),
                )
                .where(
                    TransactionModel.occurred_at >= start,
                    TransactionModel.occurred_at < end,
                )
                .group_by(TransactionModel.category)
            ).all()
            budget_rows = session.scalars(
                select(BudgetModel)
                .where(BudgetModel.month == normalized_month)
                .order_by(BudgetModel.scope)
            ).all()

        spent_by_category = {
            category: int(amount_cents or 0)
            for category, amount_cents in spending_rows
        }
        total_spent_cents = sum(spent_by_category.values())
        items: list[dict[str, Any]] = []
        total_budget: float | None = None
        for row in budget_rows:
            if row.scope == "total":
                spent_cents = total_spent_cents
                total_budget = _cents_to_amount(row.amount_cents)
            else:
                spent_cents = spent_by_category.get(row.scope, 0)
            usage = spent_cents / row.amount_cents if row.amount_cents else 0.0
            status = "exceeded" if usage > 1 else ("warning" if usage >= 0.8 else "normal")
            items.append(
                {
                    "scope": row.scope,
                    "budget": _cents_to_amount(row.amount_cents),
                    "spent": _cents_to_amount(spent_cents),
                    "usage": round(usage, 3),
                    "status": status,
                }
            )

        return {
            "month": normalized_month,
            "total_budget": total_budget,
            "total_spent": _cents_to_amount(total_spent_cents),
            "items": items,
        }
