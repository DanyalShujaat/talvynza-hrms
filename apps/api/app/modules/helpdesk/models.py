"""HR help desk tickets."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantScoped, TimestampMixin
from app.db.types import UTCDateTime

CATEGORIES = ("payroll", "attendance", "leave", "profile_update", "benefits", "policy", "general")
SLA_HOURS = {"low": 72, "normal": 48, "high": 24, "urgent": 8}


class Ticket(Base, IdMixin, TimestampMixin, TenantScoped):
    __tablename__ = "hr_tickets"

    number: Mapped[int] = mapped_column(Integer)
    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("employees.id"), index=True)
    category: Mapped[str] = mapped_column(String(30))
    priority: Mapped[str] = mapped_column(String(10), default="normal")
    subject: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)  # open|in_progress|resolved|closed
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("employees.id"), nullable=True)
    due_at: Mapped[datetime] = mapped_column(UTCDateTime)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)


class TicketComment(Base, IdMixin, TenantScoped):
    __tablename__ = "hr_ticket_comments"

    ticket_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("hr_tickets.id", ondelete="CASCADE"), index=True)
    author_identity_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    author_name: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    internal: Mapped[bool] = mapped_column(Boolean, default=False)  # visible to HR only
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
