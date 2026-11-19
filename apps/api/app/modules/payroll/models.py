"""Payroll: salary components, effective-dated salary revisions, payroll runs, entries and line items."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Numeric, String, Text, UniqueConstraint, Uuid, event, select
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantScoped, TimestampMixin
from app.db.types import UTCDateTime

MONEY = Numeric(14, 2)


class SalaryComponent(Base, IdMixin, TimestampMixin, TenantScoped):
    """kind: earning | deduction. calc: fixed (value is an amount per period) or percent_of_basic (value is a %)."""

    __tablename__ = "salary_components"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_salary_component_name"),)

    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(10))
    calc: Mapped[str] = mapped_column(String(20), default="fixed")
    default_value: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    taxable: Mapped[bool] = mapped_column(Boolean, default=True)
    # Taxable earnings only: the part up to this percent of basic salary is exempt from income tax.
    exempt_percent_of_basic: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class SalaryTemplate(Base, IdMixin, TimestampMixin, TenantScoped):
    """Reusable salary package. Applying it creates an immutable employee revision."""
    __tablename__ = "salary_templates"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_salary_template_name"),)

    name: Mapped[str] = mapped_column(String(100))
    basic: Mapped[Decimal] = mapped_column(MONEY)
    lines: Mapped[list] = mapped_column(JSON, default=list)
    increment_type: Mapped[str] = mapped_column(String(10), default="none")
    increment_value: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class SalaryRevision(Base, IdMixin, TenantScoped):
    """Revisions are never edited or overwritten: a change is a new row with a later effective date."""

    __tablename__ = "salary_revisions"
    __table_args__ = (UniqueConstraint("tenant_id", "employee_id", "effective_from", name="uq_salary_revision_date"),)

    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("employees.id"), index=True)
    template_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("salary_templates.id"), nullable=True)
    effective_from: Mapped[date] = mapped_column(Date)
    basic: Mapped[Decimal] = mapped_column(MONEY)  # amount per pay period
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class SalaryRevisionLine(Base, IdMixin, TenantScoped):
    __tablename__ = "salary_revision_lines"

    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("salary_revisions.id", ondelete="CASCADE"),
                                                   index=True)
    component_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("salary_components.id"))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)  # overrides the component default


class PayrollRun(Base, IdMixin, TimestampMixin, TenantScoped):
    __tablename__ = "payroll_runs"
    __table_args__ = (UniqueConstraint("tenant_id", "period_start", "period_end", "run_type",
                                       name="uq_payroll_run_period"),)

    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    run_type: Mapped[str] = mapped_column(String(20), default="regular")
    proration: Mapped[str] = mapped_column(String(20), default="calendar_days")
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|calculated|approved|finalized
    currency: Mapped[str] = mapped_column(String(3))
    total_gross: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))
    total_deductions: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))
    total_net: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))
    statutory_status: Mapped[str] = mapped_column(String(20), default="unconfigured")
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    finalized_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    calculated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class PayrollEntry(Base, IdMixin, TenantScoped):
    __tablename__ = "payroll_entries"
    __table_args__ = (UniqueConstraint("run_id", "employee_id", name="uq_payroll_entry_employee"),)

    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("payroll_runs.id"), index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("employees.id"), index=True)
    gross: Mapped[Decimal] = mapped_column(MONEY)
    deductions: Mapped[Decimal] = mapped_column(MONEY)
    net: Mapped[Decimal] = mapped_column(MONEY)
    unpaid_days: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0"))
    taxable_income: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    income_tax: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    employer_contributions: Mapped[dict] = mapped_column(JSON, default=dict)  # informational, not deducted
    exceptions: Mapped[list] = mapped_column(JSON, default=list)


class PayrollLineItem(Base, IdMixin, TenantScoped):
    __tablename__ = "payroll_line_items"

    entry_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("payroll_entries.id", ondelete="CASCADE"),
                                                index=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(10))  # earning | deduction
    source: Mapped[str] = mapped_column(String(20))  # basic|component|unpaid_leave|income_tax|eobi|loan|expense
    taxable: Mapped[bool] = mapped_column(Boolean, default=True)
    amount: Mapped[Decimal] = mapped_column(MONEY)


def _guard(mapper, connection, target):
    """Defence in depth: once a run is approved or finalized its entries and line items cannot be modified."""
    run_id = target.run_id if isinstance(target, PayrollEntry) else connection.execute(
        select(PayrollEntry.run_id).where(PayrollEntry.id == target.entry_id)).scalar()
    status = connection.execute(select(PayrollRun.status).where(PayrollRun.id == run_id)).scalar()
    if status in ("approved", "finalized"):
        raise PermissionError("Payroll that has been approved or finalized cannot be modified")


for _model in (PayrollEntry, PayrollLineItem):
    event.listen(_model, "before_update", _guard)
    event.listen(_model, "before_delete", _guard)
