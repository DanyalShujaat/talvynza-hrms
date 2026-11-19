"""Recruitment: jobs, candidates, applications, interviews."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantScoped, TimestampMixin
from app.db.types import UTCDateTime

DEFAULT_PIPELINE = ["Applied", "Screening", "Assessment", "Interview", "Offer", "Hired", "Rejected"]


class Job(Base, IdMixin, TimestampMixin, TenantScoped):
    __tablename__ = "jobs"

    title: Mapped[str] = mapped_column(String(160))
    department_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("departments.id"), nullable=True)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("branches.id"), nullable=True)
    designation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("designations.id"), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    employment_type: Mapped[str] = mapped_column(String(30), default="full_time")
    openings: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | open | closed
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class Candidate(Base, IdMixin, TimestampMixin, TenantScoped):
    __tablename__ = "candidates"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_candidate_email"),)

    full_name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source: Mapped[str] = mapped_column(String(40), default="manual")
    resume_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    resume_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resume_type: Mapped[str | None] = mapped_column(String(120), nullable=True)


class JobApplication(Base, IdMixin, TimestampMixin, TenantScoped):
    __tablename__ = "job_applications"
    __table_args__ = (UniqueConstraint("tenant_id", "job_id", "candidate_id", name="uq_application_once"),)

    job_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("jobs.id"), index=True)
    candidate_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("candidates.id"), index=True)
    stage: Mapped[str] = mapped_column(String(40), default="Applied")
    cover_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    employee_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("employees.id"), nullable=True)
    stage_changed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class InterviewRecord(Base, IdMixin, TenantScoped):
    __tablename__ = "interview_records"

    application_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("job_applications.id"), index=True)
    scheduled_at: Mapped[datetime] = mapped_column(UTCDateTime)
    interviewer: Mapped[str] = mapped_column(String(120))
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1 to 5 scorecard
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
