"""Attendance: policy, shifts, punches, daily summaries, correction requests."""
from __future__ import annotations

import uuid
from datetime import date, datetime, time

from sqlalchemy import JSON, Date, ForeignKey, Index, Integer, String, Text, Time, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantScoped, TimestampMixin
from app.db.types import UTCDateTime


class AttendancePolicy(Base, IdMixin, TimestampMixin, TenantScoped):
    """One row per tenant. late_mode: 'full' counts all minutes from shift start once the grace window is
    exceeded; 'grace_exempt' counts only the minutes beyond the grace window."""

    __tablename__ = "attendance_policies"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_attendance_policy_tenant"),)

    grace_minutes: Mapped[int] = mapped_column(Integer, default=10)
    late_mode: Mapped[str] = mapped_column(String(20), default="grace_exempt")
    overtime_threshold_minutes: Mapped[int] = mapped_column(Integer, default=0)
    weekend_days: Mapped[list] = mapped_column(JSON, default=lambda: [5, 6])  # Monday=0
    default_start: Mapped[time] = mapped_column(Time, default=time(9, 0))
    default_end: Mapped[time] = mapped_column(Time, default=time(18, 0))
    default_break_minutes: Mapped[int] = mapped_column(Integer, default=60)


class Shift(Base, IdMixin, TimestampMixin, TenantScoped):
    __tablename__ = "shifts"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_shift_name"),)

    name: Mapped[str] = mapped_column(String(80))
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)  # earlier than start_time means the shift ends the next day
    break_minutes: Mapped[int] = mapped_column(Integer, default=0)
    grace_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    color: Mapped[str | None] = mapped_column(String(9), nullable=True)


class ShiftAssignment(Base, IdMixin, TenantScoped):
    __tablename__ = "shift_assignments"
    __table_args__ = (Index("ix_shift_assign_emp_from", "employee_id", "effective_from"),)

    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("employees.id"))
    shift_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("shifts.id"))
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)


class AttendanceEvent(Base, IdMixin, TenantScoped):
    """Raw punch. Immutable; corrections add events or are made through approved adjustments."""

    __tablename__ = "attendance_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "employee_id", "occurred_at", "kind", name="uq_attendance_event_dedupe"),
        Index("ix_attendance_events_emp_time", "employee_id", "occurred_at"),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("employees.id"))
    kind: Mapped[str] = mapped_column(String(3))  # in | out
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime)
    source: Mapped[str] = mapped_column(String(20), default="web")  # web|manual|import|biometric|adjustment
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class AttendanceDaily(Base, IdMixin, TimestampMixin, TenantScoped):
    __tablename__ = "attendance_daily"
    __table_args__ = (UniqueConstraint("tenant_id", "employee_id", "work_date", name="uq_attendance_daily"),)

    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("employees.id"), index=True)
    work_date: Mapped[date] = mapped_column(Date, index=True)
    shift_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("shifts.id"), nullable=True)
    first_in: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_out: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    worked_minutes: Mapped[int] = mapped_column(Integer, default=0)
    late_minutes: Mapped[int] = mapped_column(Integer, default=0)
    early_leave_minutes: Mapped[int] = mapped_column(Integer, default=0)
    overtime_minutes: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="absent")
    # present | incomplete | absent | leave | holiday | weekend


class AttendanceAdjustment(Base, IdMixin, TimestampMixin, TenantScoped):
    __tablename__ = "attendance_adjustments"

    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("employees.id"), index=True)
    work_date: Mapped[date] = mapped_column(Date)
    requested_in: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    requested_out: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|approved|rejected
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
