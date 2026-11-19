"""Goals, review cycles and reviews."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantScoped, TimestampMixin
from app.db.types import UTCDateTime


class Goal(Base, IdMixin, TimestampMixin, TenantScoped):
    __tablename__ = "performance_goals"

    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("employees.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0 to 100
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | achieved | dropped
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class ReviewCycle(Base, IdMixin, TimestampMixin, TenantScoped):
    __tablename__ = "review_cycles"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_review_cycle_name"),)

    name: Mapped[str] = mapped_column(String(120))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | active | closed


class Review(Base, IdMixin, TimestampMixin, TenantScoped):
    """status: pending_self -> pending_manager -> completed. The manager's rating is hidden from the employee
    until the review is completed."""

    __tablename__ = "performance_reviews"
    __table_args__ = (UniqueConstraint("cycle_id", "employee_id", name="uq_review_cycle_employee"),)

    cycle_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("review_cycles.id"), index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("employees.id"), index=True)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("employees.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending_self")
    self_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    self_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    manager_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    manager_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
