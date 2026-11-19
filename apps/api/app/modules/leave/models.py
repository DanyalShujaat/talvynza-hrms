"""Leave: types, ledger (source of truth for balances) and requests."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantScoped, TimestampMixin
from app.db.types import UTCDateTime


class LeaveType(Base, IdMixin, TimestampMixin, TenantScoped):
    __tablename__ = "leave_types"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_leave_type_name"),)

    name: Mapped[str] = mapped_column(String(80))
    days_per_year: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0"))
    is_paid: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_negative: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_half_day: Mapped[bool] = mapped_column(Boolean, default=True)
    after_probation: Mapped[bool] = mapped_column(Boolean, default=False)
    carry_forward_max: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class LeaveLedgerEntry(Base, IdMixin, TenantScoped):
    """Append-only. entry_type: grant | carry_forward | adjustment | reserved | released | used | restored.
    days is signed: grants are positive, consumption negative, releases and restores positive."""

    __tablename__ = "leave_ledger"
    __table_args__ = (
        UniqueConstraint("tenant_id", "employee_id", "leave_type_id", "ref_key", name="uq_leave_ledger_ref"),
        Index("ix_leave_ledger_emp_type", "employee_id", "leave_type_id"),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("employees.id"))
    leave_type_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leave_types.id"))
    entry_type: Mapped[str] = mapped_column(String(20))
    days: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    effective_date: Mapped[date] = mapped_column(Date)
    request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("leave_requests.id"), nullable=True)
    ref_key: Mapped[str | None] = mapped_column(String(60), nullable=True)  # idempotency for grants and carry-forward
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class LeaveRequest(Base, IdMixin, TimestampMixin, TenantScoped):
    __tablename__ = "leave_requests"
    __table_args__ = (Index("ix_leave_req_emp_dates", "employee_id", "start_date", "end_date"),)

    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("employees.id"))
    leave_type_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leave_types.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    half_day: Mapped[bool] = mapped_column(Boolean, default=False)
    days: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|approved|rejected|cancelled
    decided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
