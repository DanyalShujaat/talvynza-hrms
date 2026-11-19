"""Reusable salary packages and atomic bulk application."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.db.session import get_db
from app.modules.common import audit, serialize_financial_writes
from app.modules.employees import service as employees
from app.modules.employees.models import LIVE_STATUSES, Employee
from app.modules.identity.deps import AuthContext, check_origin, require
from app.modules.payroll import service
from app.modules.payroll.models import SalaryComponent, SalaryRevision, SalaryTemplate

router = APIRouter(prefix="/payroll", tags=["payroll templates"],
                   dependencies=[Depends(check_origin), Depends(serialize_financial_writes)])
CENT = Decimal("0.01")


class TemplateLineIn(BaseModel):
    component_id: uuid.UUID
    amount: Decimal | None = Field(default=None, ge=0)


class TemplateIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    basic: Decimal = Field(gt=0, le=Decimal("100000000"))
    lines: list[TemplateLineIn] = Field(default_factory=list, max_length=30)
    increment_type: str = Field(default="none", pattern="^(none|percent|fixed)$")
    increment_value: Decimal = Field(default=Decimal("0"), ge=0, le=Decimal("100000000"))
    is_active: bool = True


class ApplyIn(BaseModel):
    effective_from: date
    employee_ids: list[uuid.UUID] = Field(default_factory=list, max_length=1000)
    all_employees: bool = False
    reason: str | None = Field(default=None, max_length=200)


def effective_basic(t: SalaryTemplate) -> Decimal:
    increase = t.basic * t.increment_value / 100 if t.increment_type == "percent" else (
        t.increment_value if t.increment_type == "fixed" else Decimal("0"))
    return (t.basic + increase).quantize(CENT, rounding=ROUND_HALF_UP)


def _template(t: SalaryTemplate) -> dict:
    return {"id": t.id, "name": t.name, "basic": t.basic, "lines": t.lines,
            "increment_type": t.increment_type, "increment_value": t.increment_value,
            "effective_basic": effective_basic(t), "is_active": t.is_active}


def _validated_lines(db: Session, lines: list[TemplateLineIn]) -> list[dict]:
    if len({line.component_id for line in lines}) != len(lines):
        raise ValidationFailed("A salary component can appear only once", code="duplicate_component")
    for line in lines:
        component = db.get(SalaryComponent, line.component_id)
        if component is None or not component.is_active:
            raise ValidationFailed("Choose active salary components", code="invalid_component")
    return [line.model_dump(mode="json") for line in lines]


@router.get("/templates")
def list_templates(ctx: AuthContext = Depends(require("salary.read")), db: Session = Depends(get_db)):
    return [_template(t) for t in db.scalars(select(SalaryTemplate).order_by(SalaryTemplate.name))]


@router.post("/templates", status_code=201)
def create_template(body: TemplateIn, ctx: AuthContext = Depends(require("salary.manage")),
                    db: Session = Depends(get_db)):
    name = body.name.strip()
    if db.scalar(select(SalaryTemplate.id).where(func.lower(SalaryTemplate.name) == name.lower())):
        raise Conflict("A salary template with this name exists", code="duplicate_template")
    lines = _validated_lines(db, body.lines)
    t = SalaryTemplate(tenant_id=ctx.tenant.id, name=name, basic=body.basic, lines=lines,
                       increment_type=body.increment_type, increment_value=body.increment_value,
                       is_active=body.is_active)
    db.add(t)
    db.flush()
    audit(db, ctx, "salary_template.created", "salary_template", t.id)
    db.commit()
    return _template(t)


@router.put("/templates/{template_id}")
def update_template(template_id: uuid.UUID, body: TemplateIn, ctx: AuthContext = Depends(require("salary.manage")),
                    db: Session = Depends(get_db)):
    t = db.get(SalaryTemplate, template_id)
    if t is None:
        raise NotFound("Salary template not found")
    name = body.name.strip()
    if db.scalar(select(SalaryTemplate.id).where(func.lower(SalaryTemplate.name) == name.lower(),
                                                    SalaryTemplate.id != t.id)):
        raise Conflict("A salary template with this name exists", code="duplicate_template")
    t.name, t.basic, t.lines = name, body.basic, _validated_lines(db, body.lines)
    t.increment_type, t.increment_value, t.is_active = body.increment_type, body.increment_value, body.is_active
    audit(db, ctx, "salary_template.updated", "salary_template", t.id)
    db.commit()
    return _template(t)


@router.get("/salary-roster")
def salary_roster(ctx: AuthContext = Depends(require("salary.read")), db: Session = Depends(get_db)):
    templates = {t.id: t.name for t in db.scalars(select(SalaryTemplate))}
    employees = db.scalars(select(Employee).where(Employee.deleted_at.is_(None),
                                                   Employee.status.in_(LIVE_STATUSES)).order_by(Employee.first_name))
    out = []
    for emp in employees:
        revision = db.scalar(select(SalaryRevision).where(SalaryRevision.employee_id == emp.id)
                             .order_by(SalaryRevision.effective_from.desc()).limit(1))
        out.append({"employee_id": emp.id, "employee": emp.full_name, "employee_code": emp.employee_code,
                    "basic": revision.basic if revision else None,
                    "template_id": revision.template_id if revision else None,
                    "template": templates.get(revision.template_id) if revision else None,
                    "effective_from": revision.effective_from if revision else None})
    return out


@router.post("/templates/{template_id}/apply")
def apply_template(template_id: uuid.UUID, body: ApplyIn, ctx: AuthContext = Depends(require("salary.manage")),
                   db: Session = Depends(get_db)):
    t = db.get(SalaryTemplate, template_id)
    if t is None or not t.is_active:
        raise NotFound("Active salary template not found")
    if body.all_employees and body.employee_ids:
        raise ValidationFailed("Choose employees or all employees", code="ambiguous_targets")
    if not body.all_employees and not body.employee_ids:
        raise ValidationFailed("Choose at least one employee", code="no_targets")
    if body.all_employees:
        targets = db.scalars(select(Employee).where(Employee.deleted_at.is_(None),
                                                    Employee.status.in_(LIVE_STATUSES))).all()
    else:
        targets = [employees.get_employee(db, employee_id) for employee_id in dict.fromkeys(body.employee_ids)]
    if not targets:
        raise ValidationFailed("No active employees found", code="no_targets")
    for emp in targets:
        if db.scalar(select(SalaryRevision.id).where(SalaryRevision.employee_id == emp.id,
                                                     SalaryRevision.effective_from == body.effective_from)):
            raise Conflict(f"{emp.full_name} already has a salary revision on {body.effective_from}",
                           code="duplicate_revision")
    lines = []
    for line in t.lines:
        component = db.get(SalaryComponent, uuid.UUID(line["component_id"]))
        if component is None or not component.is_active:
            raise ValidationFailed("This template has an inactive component", code="invalid_component")
        lines.append({"component_id": component.id,
                      "amount": Decimal(line["amount"]) if line.get("amount") is not None else component.default_value})
    warnings: set[str] = set()
    for emp in targets:
        _, affected = service.add_revision(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id, emp=emp,
                                           effective_from=body.effective_from, basic=effective_basic(t),
                                           lines=lines, reason=body.reason or f"Applied template: {t.name}",
                                           template_id=t.id, commit=False)
        warnings.update(affected)
    audit(db, ctx, "salary_template.applied", "salary_template", t.id,
          {"employees": len(targets), "effective_from": body.effective_from.isoformat()})
    db.commit()
    return {"template_id": t.id, "applied": len(targets), "effective_from": body.effective_from,
            "effective_basic": effective_basic(t), "finalized_periods_affected": sorted(warnings)}
