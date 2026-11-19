"""Exit process: clearance checklist, exit interview and final settlement inputs."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantScoped, TimestampMixin
from app.db.types import UTCDateTime

DEFAULT_ITEMS = [
    ("Manager", "Knowledge handover completed"),
    ("IT", "System and email access revoked"),
    ("Admin", "Company assets returned"),
    ("Finance", "Loans, advances and expenses cleared"),
    ("HR", "Exit interview held"),
    ("HR", "Final settlement approved"),
]


class Offboarding(Base, IdMixin, TimestampMixin, TenantScoped):
    __tablename__ = "offboardings"

    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("employees.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # resignation | termination | retirement
    notice_date: Mapped[date] = mapped_column(Date)
    last_working_day: Mapped[date] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_interview: Mapped[str | None] = mapped_column(Text, nullable=True)
    settlement: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="in_progress")  # in_progress | completed | cancelled
    started_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class OffboardingItem(Base, IdMixin, TenantScoped):
    __tablename__ = "offboarding_items"

    offboarding_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("offboardings.id", ondelete="CASCADE"),
                                                      index=True)
    department: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    done_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    done_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
