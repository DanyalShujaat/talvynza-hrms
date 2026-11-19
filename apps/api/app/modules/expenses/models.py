"""Expense categories and claims."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantScoped, TimestampMixin
from app.db.types import UTCDateTime


class ExpenseCategory(Base, IdMixin, TimestampMixin, TenantScoped):
    __tablename__ = "expense_categories"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_expense_category_name"),)

    name: Mapped[str] = mapped_column(String(80))
    max_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)  # per-claim limit
    requires_receipt: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ExpenseClaim(Base, IdMixin, TimestampMixin, TenantScoped):
    """status: submitted -> manager_approved -> approved -> reimbursed, or rejected / cancelled."""

    __tablename__ = "expense_claims"

    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("employees.id"), index=True)
    category_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("expense_categories.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    approved_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    expense_date: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="submitted", index=True)
    reimburse_via: Mapped[str | None] = mapped_column(String(10), nullable=True)  # payroll | direct
    payroll_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("payroll_runs.id"), nullable=True)
    manager_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    finance_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    manager_decided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    finance_decided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    reimbursed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    receipt_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    receipt_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    receipt_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    receipt_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
