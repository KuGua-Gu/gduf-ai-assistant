"""成员 2 的业务数据表模型。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import CheckConstraint, Date, DateTime, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """业务表声明式基类。"""


class TransactionModel(Base):
    """账单表。金额以分为单位保存，避免浮点精度误差。"""

    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="ck_transactions_amount_positive"),
        CheckConstraint(
            "source IN ('text', 'ocr', 'manual')",
            name="ck_transactions_source",
        ),
        Index("ix_transactions_occurred_at", "occurred_at"),
        Index("ix_transactions_category", "category"),
        Index("ix_transactions_category_occurred_at", "category", "occurred_at"),
        Index(
            "uq_transactions_demo_seed_session",
            "session_id",
            unique=True,
            sqlite_where=text("session_id LIKE 'demo-seed:%'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    merchant: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    occurred_at: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    session_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class BudgetModel(Base):
    """月度预算表：同一月份和预算范围只保留一条记录。"""

    __tablename__ = "budgets"
    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="ck_budgets_amount_positive"),
        UniqueConstraint("month", "scope", name="uq_budgets_month_scope"),
        Index("ix_budgets_month", "month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    scope: Mapped[str] = mapped_column(String(50), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
