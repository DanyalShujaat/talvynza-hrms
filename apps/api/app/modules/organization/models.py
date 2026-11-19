"""Organization structure: branches, departments, designations, holidays."""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantScoped, TimestampMixin


class Branch(Base, IdMixin, TimestampMixin, TenantScoped):
    __tablename__ = "branches"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_branches_tenant_name"),)

    name: Mapped[str] = mapped_column(String(120))
    code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Department(Base, IdMixin, TimestampMixin, TenantScoped):
    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_departments_tenant_name"),)

    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("departments.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Designation(Base, IdMixin, TimestampMixin, TenantScoped):
    __tablename__ = "designations"
    __table_args__ = (UniqueConstraint("tenant_id", "department_id", "name", name="uq_designation_dept_name"),)

    name: Mapped[str] = mapped_column(String(120))
    department_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("departments.id"), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(20), nullable=True)


class Holiday(Base, IdMixin, TenantScoped):
    __tablename__ = "holidays"
    __table_args__ = (UniqueConstraint("tenant_id", "holiday_date", "branch_id", name="uq_holiday_date_branch"),)

    holiday_date: Mapped[date] = mapped_column(Date, index=True)
    name: Mapped[str] = mapped_column(String(120))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("branches.id"), nullable=True)
