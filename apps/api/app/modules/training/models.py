"""Training courses and enrollments."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantScoped, TimestampMixin


class Course(Base, IdMixin, TimestampMixin, TenantScoped):
    __tablename__ = "training_courses"
    __table_args__ = (UniqueConstraint("tenant_id", "title", name="uq_course_title"),)

    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(60), default="General")
    mandatory: Mapped[bool] = mapped_column(Boolean, default=False)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    duration_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 1), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Enrollment(Base, IdMixin, TimestampMixin, TenantScoped):
    __tablename__ = "training_enrollments"
    __table_args__ = (UniqueConstraint("course_id", "employee_id", name="uq_enrollment_once"),)

    course_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("training_courses.id"), index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("employees.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="assigned")  # assigned | in_progress | completed
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
