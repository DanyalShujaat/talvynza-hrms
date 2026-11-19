"""Employees: profile, effective-dated assignments, lifecycle events, education, documents, checklist."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, SoftDeleteMixin, TenantScoped, TimestampMixin
from app.db.types import EncryptedString, UTCDateTime

STATUSES = ("active", "probation", "suspended", "resigned", "terminated", "retired", "inactive")
LIVE_STATUSES = ("active", "probation", "suspended")


class Employee(Base, IdMixin, TimestampMixin, SoftDeleteMixin, TenantScoped):
    __tablename__ = "employees"
    __table_args__ = (
        UniqueConstraint("tenant_id", "employee_code", name="uq_employee_code"),
        Index("ix_employees_tenant_status", "tenant_id", "status"),
    )

    employee_code: Mapped[str] = mapped_column(String(30))
    bio_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    membership_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tenant_memberships.id"), nullable=True, unique=True
    )
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str] = mapped_column(String(80))
    preferred_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    nationality: Mapped[str | None] = mapped_column(String(60), nullable=True)
    national_id: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    address: Mapped[str | None] = mapped_column(String(400), nullable=True)
    emergency_contacts: Mapped[list] = mapped_column(JSON, default=list)

    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("branches.id"), nullable=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("departments.id"), nullable=True)
    designation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("designations.id"), nullable=True)
    manager_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("employees.id"), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="active")
    employment_type: Mapped[str] = mapped_column(String(30), default="full_time")
    contract_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    contract_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    work_location: Mapped[str | None] = mapped_column(String(80), nullable=True)
    joining_date: Mapped[date] = mapped_column(Date)
    probation_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    confirmation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    exit_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    payment_method: Mapped[str | None] = mapped_column(String(30), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    bank_account: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class EmployeeAssignment(Base, IdMixin, TenantScoped):
    """Effective-dated organizational placement. Rows are closed, never deleted."""

    __tablename__ = "employee_assignments"

    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("employees.id"), index=True)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("branches.id"), nullable=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("departments.id"), nullable=True)
    designation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("designations.id"), nullable=True)
    manager_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("employees.id"), nullable=True)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)


class EmployeeLifecycleEvent(Base, IdMixin, TenantScoped):
    __tablename__ = "employee_lifecycle_events"

    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("employees.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(30))
    effective_date: Mapped[date] = mapped_column(Date)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class EmployeeEducation(Base, IdMixin, TimestampMixin, TenantScoped):
    __tablename__ = "employee_education"

    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("employees.id"), index=True)
    level: Mapped[str] = mapped_column(String(60))
    degree: Mapped[str] = mapped_column(String(120))
    institute: Mapped[str | None] = mapped_column(String(160), nullable=True)
    obtained_marks: Mapped[str | None] = mapped_column(String(20), nullable=True)
    total_marks: Mapped[str | None] = mapped_column(String(20), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(20), nullable=True)
    division: Mapped[str | None] = mapped_column(String(40), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)


class EmployeeDocument(Base, IdMixin, TenantScoped):
    __tablename__ = "employee_documents"

    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("employees.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(40), default="other")
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(300))
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class ChecklistItem(Base, IdMixin, TenantScoped):
    __tablename__ = "employee_checklist_items"

    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("employees.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    done_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
