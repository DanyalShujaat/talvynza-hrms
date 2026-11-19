"""Notices (company announcements), in-app notifications and tasks."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantScoped, TimestampMixin
from app.db.types import UTCDateTime


class Notice(Base, IdMixin, TimestampMixin, TenantScoped):
    __tablename__ = "notices"

    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    # Audience: everyone when both are null; otherwise matching branch or department only.
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("branches.id"), nullable=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("departments.id"), nullable=True)
    author_identity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    published_at: Mapped[datetime] = mapped_column(UTCDateTime)


class Notification(Base, IdMixin, TenantScoped):
    """In-app notification addressed to one membership. Email delivery is queued separately."""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_member_read", "membership_id", "read_at"),)

    membership_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenant_memberships.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    link: Mapped[str | None] = mapped_column(String(200), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class Task(Base, IdMixin, TimestampMixin, TenantScoped):
    __tablename__ = "tasks"

    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    assignee_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("employees.id"), index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="todo")  # todo | in_progress | blocked | done
    priority: Mapped[str] = mapped_column(String(10), default="normal")  # low | normal | high
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
