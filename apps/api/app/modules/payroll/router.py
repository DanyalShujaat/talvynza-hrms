from __future__ import annotations

import csv
import io
import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.db.session import get_db
from app.modules.common import audit, serialize_financial_writes
from app.modules.employees import service as emp_service
from app.modules.employees.models import Employee
from app.modules.identity.deps import AuthContext, check_origin, require
from app.modules.payroll import service
from app.modules.payroll.models import (
    PayrollEntry,
    PayrollRun,
    SalaryComponent,
    SalaryRevision,
    SalaryRevisionLine,
)
from app.modules.payroll.statutory import pk

router = APIRouter(tags=["payroll"], dependencies=[Depends(check_origin), Depends(serialize_financial_writes)])


class ComponentIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    kind: str = Field(pattern="^(earning|deduction)$")
    calc: str = Field(default="fixed", pattern="^(fixed|percent_of_basic)$")
    default_value: Decimal = Field(default=Decimal("0"), ge=0, le=Decimal("100000000"))
    taxable: bool = True
    exempt_percent_of_basic: Decimal | None = Field(default=None, ge=0, le=100)
    is_active: bool = True


class RevisionLineIn(BaseModel):
    component_id: uuid.UUID
    amount: Decimal | None = Field(default=None, ge=0)


class RevisionIn(BaseModel):
    effective_from: date
    basic: Decimal = Field(gt=0, le=Decimal("100000000"))
    lines: list[RevisionLineIn] = Field(default_factory=list, max_length=30)
    reason: str | None = Field(default=None, max_length=200)


class RunIn(BaseModel):
    period_start: date
    period_end: date
    proration: str = Field(default="calendar_days", pattern="^(calendar_days|working_days)$")
    note: str | None = Field(default=None, max_length=500)


class StatutoryIn(BaseModel):
    income_tax: bool
    eobi_enabled: bool
    eobi_wage_base: Decimal | None = Field(default=None, gt=0, le=Decimal("10000000"))
    eobi_employee_percent: Decimal = Field(default=Decimal("1"), ge=0, le=100)
    eobi_employer_percent: Decimal = Field(default=Decimal("5"), ge=0, le=100)


def _comp(c: SalaryComponent) -> dict:
    return {"id": c.id, "name": c.name, "kind": c.kind, "calc": c.calc, "default_value": c.default_value,
            "taxable": c.taxable, "exempt_percent_of_basic": c.exempt_percent_of_basic, "is_active": c.is_active}


def _run(r: PayrollRun, ctx: AuthContext) -> dict:
    return {"id": r.id, "period_start": r.period_start, "period_end": r.period_end, "proration": r.proration,
            "status": r.status, "currency": r.currency, "total_gross": r.total_gross,
            "total_deductions": r.total_deductions, "total_net": r.total_net,
            "statutory_status": r.statutory_status, "statutory_notice": service.statutory_notice(r, ctx.tenant),
            "created_by": r.created_by, "approved_by": r.approved_by, "calculated_at": r.calculated_at,
            "approved_at": r.approved_at, "finalized_at": r.finalized_at, "note": r.note}


# ------------------------------------------------------------------ statutory settings
@router.get("/payroll/statutory")
def get_statutory(ctx: AuthContext = Depends(require("payroll.read"))):
    cfg = service.statutory_config(ctx.tenant)
    current = pk.tax_year_of(date.today())
    return {**cfg, "current_tax_year": current, "current_rules_loaded": current in pk.TAX_YEARS,
            "tax_years": [pk.describe(t) for _, t in sorted(pk.TAX_YEARS.items(), reverse=True)] if cfg["supported"] else []}


@router.put("/payroll/statutory")
def put_statutory(body: StatutoryIn, ctx: AuthContext = Depends(require("salary.manage", "payroll.read")),
                  db: Session = Depends(get_db)):
    if ctx.tenant.country != "PK":
        raise Conflict("Statutory rules are only available for organizations in Pakistan", code="unsupported_country")
    if body.eobi_enabled and body.eobi_wage_base is None:
        raise ValidationFailed("Enter the wage base EOBI is charged on before switching it on",
                               details=[{"field": "eobi_wage_base"}])
    ctx.tenant.settings = {**ctx.tenant.settings, "statutory": body.model_dump(mode="json")}
    audit(db, ctx, "payroll.statutory_changed", "tenant", ctx.tenant.id, body.model_dump(mode="json"))
    db.commit()
    return service.statutory_config(ctx.tenant)


# ------------------------------------------------------------------ components
@router.get("/payroll/components")
def list_components(ctx: AuthContext = Depends(require("salary.read")), db: Session = Depends(get_db)):
    return [_comp(c) for c in db.scalars(select(SalaryComponent).order_by(SalaryComponent.kind.desc(), SalaryComponent.name))]


@router.post("/payroll/components", status_code=201)
def create_component(body: ComponentIn, ctx: AuthContext = Depends(require("salary.manage")),
                     db: Session = Depends(get_db)):
    if db.scalar(select(func.count()).select_from(SalaryComponent).where(
            func.lower(SalaryComponent.name) == body.name.lower())):
        raise Conflict("A component with this name exists", code="duplicate_name")
    c = SalaryComponent(tenant_id=ctx.tenant.id, **body.model_dump())
    db.add(c)
    db.flush()
    audit(db, ctx, "salary_component.created", "salary_component", c.id, {"name": c.name})
    db.commit()
    return _comp(c)


@router.put("/payroll/components/{component_id}")
def update_component(component_id: uuid.UUID, body: ComponentIn, ctx: AuthContext = Depends(require("salary.manage")),
                     db: Session = Depends(get_db)):
    c = db.get(SalaryComponent, component_id)
    if c is None:
        raise NotFound("Component not found")
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    audit(db, ctx, "salary_component.updated", "salary_component", c.id)
    db.commit()
    return _comp(c)


# ------------------------------------------------------------------ salary revisions
@router.get("/employees/{employee_id}/salary")
def salary_history(employee_id: uuid.UUID, ctx: AuthContext = Depends(require("salary.read")),
                   db: Session = Depends(get_db)):
    emp = emp_service.get_employee(db, employee_id)
    comps = {c.id: c for c in db.scalars(select(SalaryComponent))}
    out = []
    for r in db.scalars(select(SalaryRevision).where(SalaryRevision.employee_id == emp.id)
                        .order_by(SalaryRevision.effective_from.desc())):
        lines = [{"component_id": ln.component_id, "name": comps[ln.component_id].name,
                  "kind": comps[ln.component_id].kind, "calc": comps[ln.component_id].calc,
                  "amount": ln.amount if ln.amount is not None else comps[ln.component_id].default_value}
                 for ln in db.scalars(select(SalaryRevisionLine).where(SalaryRevisionLine.revision_id == r.id))
                 if ln.component_id in comps]
        out.append({"id": r.id, "effective_from": r.effective_from, "basic": r.basic, "reason": r.reason,
                    "template_id": r.template_id,
                    "lines": lines})
    return out


@router.post("/employees/{employee_id}/salary", status_code=201)
def add_revision(employee_id: uuid.UUID, body: RevisionIn, ctx: AuthContext = Depends(require("salary.manage")),
                 db: Session = Depends(get_db)):
    emp = emp_service.get_employee(db, employee_id)
    rev, affected = service.add_revision(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id, emp=emp,
                                         effective_from=body.effective_from, basic=body.basic,
                                         lines=[ln.model_dump() for ln in body.lines], reason=body.reason)
    return {"id": rev.id, "effective_from": rev.effective_from, "basic": rev.basic,
            "warning": (f"This date is inside finalized payroll periods ({', '.join(affected)}). Those runs are not "
                        "changed; handle the difference as an adjustment in a later run.") if affected else None}


# ------------------------------------------------------------------ runs
@router.get("/payroll/runs")
def list_runs(ctx: AuthContext = Depends(require("payroll.read")), db: Session = Depends(get_db)):
    return [_run(r, ctx) for r in db.scalars(select(PayrollRun).order_by(PayrollRun.period_start.desc()))]


@router.post("/payroll/runs", status_code=201)
def create_run(body: RunIn, ctx: AuthContext = Depends(require("payroll.process")), db: Session = Depends(get_db)):
    return _run(service.create_run(db, tenant=ctx.tenant, actor=ctx.identity.id, start=body.period_start,
                                   end=body.period_end, proration=body.proration, note=body.note), ctx)


@router.get("/payroll/runs/{run_id}")
def get_run(run_id: uuid.UUID, ctx: AuthContext = Depends(require("payroll.read")), db: Session = Depends(get_db)):
    run = service.get_run(db, run_id)
    names = {e.id: e for e in db.scalars(select(Employee))}
    depts = emp_service.name_maps(db)["department"]
    rows = [e for e in db.scalars(select(PayrollEntry).where(PayrollEntry.run_id == run.id)) if e.employee_id in names]
    entries = [{"id": e.id, "employee_id": e.employee_id, "employee": names[e.employee_id].full_name,
                "employee_code": names[e.employee_id].employee_code,
                "department": depts.get(names[e.employee_id].department_id), "gross": e.gross,
                "deductions": e.deductions, "net": e.net, "income_tax": e.income_tax,
                "taxable_income": e.taxable_income, "unpaid_days": e.unpaid_days, "exceptions": e.exceptions}
               for e in rows]
    employer = sum((Decimal(v) for e in rows for v in (e.employer_contributions or {}).values()), Decimal("0"))
    return {**_run(run, ctx), "entries": sorted(entries, key=lambda x: x["employee"]),
            "total_income_tax": sum((e.income_tax for e in rows), Decimal("0")),
            "total_employer_contributions": employer}


@router.post("/payroll/runs/{run_id}/calculate")
def calculate(run_id: uuid.UUID, ctx: AuthContext = Depends(require("payroll.process")),
              db: Session = Depends(get_db)):
    run = service.get_run(db, run_id)
    summary = service.calculate_run(db, tenant=ctx.tenant, actor=ctx.identity.id, run=run)
    return {**summary, "run": _run(run, ctx)}


@router.post("/payroll/runs/{run_id}/approve")
def approve(run_id: uuid.UUID, ctx: AuthContext = Depends(require("payroll.approve")), db: Session = Depends(get_db)):
    return _run(service.approve_run(db, tenant=ctx.tenant, actor=ctx.identity.id, run=service.get_run(db, run_id)), ctx)


@router.post("/payroll/runs/{run_id}/finalize")
def finalize(run_id: uuid.UUID, ctx: AuthContext = Depends(require("payroll.approve")), db: Session = Depends(get_db)):
    return _run(service.finalize_run(db, tenant=ctx.tenant, actor=ctx.identity.id, run=service.get_run(db, run_id)), ctx)


@router.delete("/payroll/runs/{run_id}", status_code=204)
def delete_run(run_id: uuid.UUID, ctx: AuthContext = Depends(require("payroll.process")),
               db: Session = Depends(get_db)):
    service.delete_run(db, tenant=ctx.tenant, actor=ctx.identity.id, run=service.get_run(db, run_id))


@router.get("/payroll/runs/{run_id}/variance")
def variance(run_id: uuid.UUID, ctx: AuthContext = Depends(require("payroll.read")), db: Session = Depends(get_db)):
    return service.variance(db, service.get_run(db, run_id))


@router.get("/payroll/runs/{run_id}/exceptions")
def exceptions(run_id: uuid.UUID, ctx: AuthContext = Depends(require("payroll.read")), db: Session = Depends(get_db)):
    return service.exceptions_of(db, service.get_run(db, run_id))


def _slip(db: Session, ctx: AuthContext, run: PayrollRun, e: PayrollEntry, emp: Employee) -> dict:
    lines = service.get_entry_with_lines(db, e)
    names = emp_service.name_maps(db)
    order = {"basic": 0, "component": 1, "expense": 2, "income_tax": 0, "eobi": 1, "unpaid_leave": 2, "loan": 3}
    lines.sort(key=lambda x: (order.get(x.source, 9), x.name))
    return {"entry_id": e.id, "organization": ctx.tenant.name, "employee": emp.full_name,
            "employee_code": emp.employee_code, "department": names["department"].get(emp.department_id),
            "designation": names["designation"].get(emp.designation_id), "joining_date": emp.joining_date,
            "period_start": run.period_start, "period_end": run.period_end,
            "currency": run.currency, "gross": e.gross, "deductions": e.deductions, "net": e.net,
            "taxable_income": e.taxable_income, "income_tax": e.income_tax, "unpaid_days": e.unpaid_days,
            "finalized_at": run.finalized_at, "status": run.status,
            "earnings": [{"name": x.name, "amount": x.amount} for x in lines if x.kind == "earning"],
            "deduction_lines": [{"name": x.name, "amount": x.amount} for x in lines if x.kind == "deduction"],
            "employer_contributions": [{"name": k, "amount": v} for k, v in (e.employer_contributions or {}).items()],
            "statutory_notice": service.statutory_notice(run, ctx.tenant)}


@router.get("/payroll/runs/{run_id}/entries/{entry_id}")
def run_entry(run_id: uuid.UUID, entry_id: uuid.UUID, ctx: AuthContext = Depends(require("payroll.read")),
              db: Session = Depends(get_db)):
    run = service.get_run(db, run_id)
    e = db.scalar(select(PayrollEntry).where(PayrollEntry.id == entry_id, PayrollEntry.run_id == run.id))
    if e is None:
        raise NotFound("Entry not found")
    return _slip(db, ctx, run, e, emp_service.get_employee(db, e.employee_id))


@router.get("/payroll/runs/{run_id}/export.csv")
def export_payments(run_id: uuid.UUID, ctx: AuthContext = Depends(require("payroll.read", "bank.read")),
                    db: Session = Depends(get_db)):
    """Bank payment file. Finalized runs only; every export is audited."""
    run = service.get_run(db, run_id)
    if run.status != "finalized":
        raise Conflict("Only finalized runs can be exported", code="not_finalized")
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["employee_code", "employee_name", "bank_name", "account", "amount", "currency", "reference"])
    for e in db.scalars(select(PayrollEntry).where(PayrollEntry.run_id == run.id)):
        emp = db.get(Employee, e.employee_id)
        w.writerow([emp.employee_code, emp.full_name, emp.bank_name or "", emp.bank_account or "", f"{e.net:.2f}",
                    run.currency, f"PAY-{run.period_start:%Y%m}-{emp.employee_code}"])
    audit(db, ctx, "payroll.exported", "payroll_run", run.id)
    db.commit()
    return Response(out.getvalue(), media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="payments-{run.period_start}-{run.period_end}.csv"'})


# ------------------------------------------------------------------ payslips (self service)
@router.get("/payslips")
def my_payslips(ctx: AuthContext = Depends(require("payslip.read_own")), db: Session = Depends(get_db)):
    me = emp_service.current_employee(db, ctx.membership.id)
    if me is None:
        return []
    rows = db.execute(select(PayrollEntry, PayrollRun).join(PayrollRun, PayrollRun.id == PayrollEntry.run_id).where(
        PayrollEntry.employee_id == me.id, PayrollRun.status == "finalized").order_by(PayrollRun.period_start.desc()))
    return [{"entry_id": e.id, "period_start": r.period_start, "period_end": r.period_end, "gross": e.gross,
             "deductions": e.deductions, "income_tax": e.income_tax, "net": e.net, "currency": r.currency}
            for e, r in rows]


@router.get("/payslips/{entry_id}")
def payslip(entry_id: uuid.UUID, ctx: AuthContext = Depends(require("payslip.read_own")),
            db: Session = Depends(get_db)):
    me = emp_service.current_employee(db, ctx.membership.id)
    e = db.get(PayrollEntry, entry_id)
    run = db.get(PayrollRun, e.run_id) if e else None
    # Someone else's payslip, an unfinalized run and a missing id all look identical.
    if e is None or me is None or e.employee_id != me.id or run is None or run.status != "finalized":
        raise NotFound("Payslip not found")
    return _slip(db, ctx, run, e, me)
