"""Employee loans and salary advances with a repayment schedule."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantScoped, TimestampMixin
from app.db.types import UTCDateTime


class Loan(Base, IdMixin, TimestampMixin, TenantScoped):
    """status: requested -> approved -> active -> closed, or rejected / cancelled."""

    __tablename__ = "loans"

    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("employees.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # loan | advance
    principal: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    installments: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="requested", index=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    disbursed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class LoanInstallment(Base, IdMixin, TenantScoped):
    """payroll_run_id is set while a payroll run includes the installment, which blocks a second, manual payment."""

    __tablename__ = "loan_installments"

    loan_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("loans.id", ondelete="CASCADE"), index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("employees.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(String(10), default="due")  # due | paid
    method: Mapped[str | None] = mapped_column(String(10), nullable=True)  # payroll | manual
    paid_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    payroll_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("payroll_runs.id"), nullable=True)
