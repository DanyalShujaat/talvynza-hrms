"""Payroll workflow: draft, calculate, approve, finalize. Finalized runs are immutable."""
from __future__ import annotations

import calendar
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.db.base import utcnow
from app.modules.employees.models import LIVE_STATUSES, Employee
from app.modules.expenses.models import ExpenseClaim
from app.modules.leave import service as leave_service
from app.modules.leave.models import LeaveRequest, LeaveType
from app.modules.loans.models import Loan, LoanInstallment
from app.modules.notifications.service import notify_employee
from app.modules.payroll import engine
from app.modules.payroll.models import (
    PayrollEntry,
    PayrollLineItem,
    PayrollRun,
    SalaryComponent,
    SalaryRevision,
    SalaryRevisionLine,
)
from app.modules.payroll.statutory import pk
from app.modules.tenancy import service as tenancy
from app.modules.tenancy.models import Tenant

ZERO = Decimal("0")
LIMITS = "Tax credits, income from other employers and the valuation of perquisites are not included."


# ------------------------------------------------------------------ statutory configuration
def statutory_config(tenant: Tenant) -> dict:
    """Pakistan income tax is on by default for organizations in Pakistan. EOBI stays off until the wage base
    it is charged on has been entered, because that figure follows the notified minimum wage."""
    cfg = dict(tenant.settings.get("statutory") or {})
    is_pk = tenant.country == "PK"
    return {
        "country": tenant.country, "supported": is_pk,
        "income_tax": bool(cfg.get("income_tax", True)) and is_pk,
        "eobi_enabled": bool(cfg.get("eobi_enabled", False)) and is_pk,
        "eobi_wage_base": cfg.get("eobi_wage_base"),
        "eobi_employee_percent": cfg.get("eobi_employee_percent", "1"),
        "eobi_employer_percent": cfg.get("eobi_employer_percent", "5"),
    }


def is_calendar_month(start: date, end: date) -> bool:
    return (start.day == 1 and start.year == end.year and start.month == end.month
            and end.day == calendar.monthrange(end.year, end.month)[1])


def statutory_notice(run: PayrollRun, tenant: Tenant) -> str:
    s = run.statutory_status or "unconfigured"
    if s.startswith("pk:ty"):
        year = int(s[5:9])
        ty = pk.TAX_YEARS[year]
        text = f"Income tax is withheld at the Pakistan salaried rates for tax year {year} ({ty.law}). {LIMITS}"
        if s.endswith("+eobi"):
            text += " EOBI is deducted on the wage base set in the statutory settings."
        return text
    if s.startswith("pk:no_rules"):
        return (f"No verified income tax rates are loaded for tax year {s.rsplit(':', 1)[1]}, so no income tax was "
                "withheld in this run.")
    if s == "pk:not_monthly":
        return ("Income tax is calculated only for pay periods that cover one full calendar month. None was "
                "withheld in this run.")
    if s == "pk:eobi_only":
        return "Income tax withholding is switched off. EOBI is deducted on the wage base set in the statutory settings."
    if s == "pk:off":
        return "Statutory deductions are switched off in this organization's payroll settings."
    return (f"Statutory deductions (income tax, social insurance, pension) are not available for {tenant.country}, "
            "so none have been calculated.")


# ------------------------------------------------------------------ salary
def load_revisions(db: Session, employee_id: uuid.UUID) -> list[engine.Revision]:
    comps = {c.id: c for c in db.scalars(select(SalaryComponent))}
    out = []
    for r in db.scalars(select(SalaryRevision).where(SalaryRevision.employee_id == employee_id)
                        .order_by(SalaryRevision.effective_from)):
        lines = []
        for ln in db.scalars(select(SalaryRevisionLine).where(SalaryRevisionLine.revision_id == r.id)):
            c = comps.get(ln.component_id)
            if c is None or not c.is_active:
                continue
            value = ln.amount if ln.amount is not None else c.default_value
            lines.append(engine.Line(c.name, c.kind, c.calc, Decimal(value), c.taxable, c.exempt_percent_of_basic))
        out.append(engine.Revision(r.effective_from, Decimal(r.basic), tuple(lines)))
    return out


def add_revision(db: Session, *, tenant_id: uuid.UUID, actor: uuid.UUID, emp: Employee, effective_from: date,
                 basic: Decimal, lines: list[dict], reason: str | None, template_id: uuid.UUID | None = None,
                 commit: bool = True) -> tuple[SalaryRevision, list[str]]:
    if basic <= 0:
        raise ValidationFailed("Basic salary must be greater than zero", details=[{"field": "basic"}])
    if db.scalar(select(func.count()).select_from(SalaryRevision).where(
            SalaryRevision.employee_id == emp.id, SalaryRevision.effective_from == effective_from)):
        raise Conflict("A salary revision already exists for that date. Revisions are never overwritten.",
                       code="duplicate_revision")
    rev = SalaryRevision(tenant_id=tenant_id, employee_id=emp.id, effective_from=effective_from, basic=basic,
                         reason=reason, template_id=template_id, created_by=actor, created_at=utcnow())
    db.add(rev)
    db.flush()
    for ln in lines:
        comp = db.get(SalaryComponent, ln["component_id"])
        if comp is None:
            raise ValidationFailed("Unknown salary component", details=[{"field": "lines"}])
        db.add(SalaryRevisionLine(tenant_id=tenant_id, revision_id=rev.id, component_id=comp.id,
                                  amount=ln.get("amount")))
    affected = [f"{r.period_start}..{r.period_end}" for r in db.scalars(select(PayrollRun).where(
        PayrollRun.status == "finalized", PayrollRun.period_end >= effective_from))]
    tenancy.record_audit(db, tenant_id=tenant_id, actor=actor, action="salary.revised", entity_type="employee",
                         entity_id=emp.id, details={"effective_from": effective_from.isoformat(), "reason": reason})
    notify_employee(db, emp, "salary", "A salary update has been scheduled",
                    f"Effective from {effective_from}", "/me/payslips")
    if commit:
        db.commit()
    return rev, affected


# ------------------------------------------------------------------ runs
def _lock_finance(db: Session, tenant: Tenant, run: PayrollRun | None = None) -> None:
    # Serialize payroll writes per organization on PostgreSQL, including different runs
    # competing for the same reimbursements. Refresh objects loaded before the lock.
    db.execute(select(Tenant.id).where(Tenant.id == tenant.id).with_for_update()).scalar_one()
    if run is not None:
        db.refresh(run)


def create_run(db: Session, *, tenant: Tenant, actor: uuid.UUID, start: date, end: date, proration: str,
               note: str | None) -> PayrollRun:
    _lock_finance(db, tenant)
    if end < start:
        raise ValidationFailed("Period end is before its start", details=[{"field": "period_end"}])
    if (end - start).days > 366:
        raise ValidationFailed("A pay period cannot be longer than a year", code="period_too_long")
    if proration not in ("calendar_days", "working_days"):
        raise ValidationFailed("Unknown proration method", details=[{"field": "proration"}])
    if db.scalar(select(func.count()).select_from(PayrollRun).where(
            PayrollRun.period_start == start, PayrollRun.period_end == end, PayrollRun.run_type == "regular")):
        raise Conflict("A payroll run already exists for this period", code="duplicate_run")
    if db.scalar(select(PayrollRun.id).where(
            PayrollRun.period_start <= end, PayrollRun.period_end >= start, PayrollRun.run_type == "regular")):
        raise Conflict("This period overlaps another payroll run. Choose a separate period.", code="overlapping_run")
    run = PayrollRun(tenant_id=tenant.id, period_start=start, period_end=end, proration=proration,
                     currency=tenant.currency, status="draft", created_by=actor, note=note)
    db.add(run)
    tenancy.record_audit(db, tenant_id=tenant.id, actor=actor, action="payroll.run_created",
                         entity_type="payroll_run", details={"period": f"{start}..{end}"})
    db.commit()
    return run


def _unpaid_days(db: Session, emp: Employee, a: date, b: date) -> Decimal:
    unpaid_types = {t.id for t in db.scalars(select(LeaveType).where(LeaveType.is_paid.is_(False)))}
    if not unpaid_types or a > b:
        return ZERO
    total = ZERO
    for r in db.scalars(select(LeaveRequest).where(
            LeaveRequest.employee_id == emp.id, LeaveRequest.status == "approved",
            LeaveRequest.leave_type_id.in_(unpaid_types), LeaveRequest.start_date <= b,
            LeaveRequest.end_date >= a)):
        lo, hi = max(r.start_date, a), min(r.end_date, b)
        days = leave_service.count_working_days(db, lo, hi, emp.branch_id)
        total += Decimal("0.5") if r.half_day else Decimal(days)
    return total


def _release(db: Session, run: PayrollRun) -> None:
    """Drops the run's entries and frees the loan installments and expense claims it had picked up."""
    db.execute(update(LoanInstallment).where(LoanInstallment.payroll_run_id == run.id,
                                             LoanInstallment.status == "due").values(payroll_run_id=None))
    db.execute(update(ExpenseClaim).where(ExpenseClaim.payroll_run_id == run.id,
                                          ExpenseClaim.status == "approved").values(payroll_run_id=None))
    ids = list(db.scalars(select(PayrollEntry.id).where(PayrollEntry.run_id == run.id)))
    if ids:
        db.execute(delete(PayrollLineItem).where(PayrollLineItem.entry_id.in_(ids)))
        db.execute(delete(PayrollEntry).where(PayrollEntry.run_id == run.id))
    db.flush()


def _ytd(db: Session, employee_id: uuid.UUID, ty: pk.TaxYear, before: date) -> tuple[Decimal, Decimal]:
    """Taxable pay and tax withheld in finalized runs earlier in the same tax year."""
    row = db.execute(select(func.coalesce(func.sum(PayrollEntry.taxable_income), 0),
                            func.coalesce(func.sum(PayrollEntry.income_tax), 0))
                     .join(PayrollRun, PayrollRun.id == PayrollEntry.run_id)
                     .where(PayrollEntry.employee_id == employee_id, PayrollRun.status == "finalized",
                            PayrollRun.period_end >= ty.start, PayrollRun.period_end < before)).one()
    return Decimal(str(row[0])), Decimal(str(row[1]))


def calculate_run(db: Session, *, tenant: Tenant, actor: uuid.UUID, run: PayrollRun) -> dict:
    _lock_finance(db, tenant, run)
    if run.status not in ("draft", "calculated"):
        raise Conflict("Only draft or calculated runs can be recalculated", code="run_locked")
    _release(db, run)
    cfg = statutory_config(tenant)
    monthly = is_calendar_month(run.period_start, run.period_end)
    ty_number = pk.tax_year_of(run.period_end)
    ty = pk.TAX_YEARS.get(ty_number)
    tax_on = cfg["income_tax"] and monthly and ty is not None
    eobi_on = bool(cfg["eobi_enabled"] and monthly and cfg["eobi_wage_base"])
    if not cfg["supported"]:
        run.statutory_status = "unconfigured"
    elif not cfg["income_tax"] and not cfg["eobi_enabled"]:
        run.statutory_status = "pk:off"
    elif not monthly:
        run.statutory_status = "pk:not_monthly"
    elif cfg["income_tax"] and ty is None:
        run.statutory_status = f"pk:no_rules:{ty_number}"
    elif tax_on:
        run.statutory_status = f"pk:ty{ty_number}" + ("+eobi" if eobi_on else "")
    else:
        run.statutory_status = "pk:eobi_only" if eobi_on else "pk:off"

    emps = db.scalars(select(Employee).where(
        Employee.deleted_at.is_(None), Employee.joining_date <= run.period_end,
        (Employee.exit_date.is_(None)) | (Employee.exit_date >= run.period_start),
        Employee.status.in_(LIVE_STATUSES + ("resigned", "terminated", "retired")))).all()
    totals = [ZERO, ZERO, ZERO]
    skipped, entries = [], 0
    far = date(9999, 12, 31)
    for emp in emps:
        revisions = load_revisions(db, emp.id)
        if not revisions:
            skipped.append({"employee": emp.full_name, "reason": "no salary on file"})
            continue
        branch = emp.branch_id
        counter = (engine.calendar_days if run.proration == "calendar_days"
                   else (lambda a, b, br=branch: leave_service.count_working_days(db, a, b, br)))
        active_start, active_end = emp.joining_date, emp.exit_date or far
        lo, hi = max(run.period_start, active_start), min(run.period_end, active_end)
        unpaid = _unpaid_days(db, emp, lo, hi)
        res = engine.calculate(
            run.period_start, run.period_end, revisions, count_days=counter,
            working_days_in_period=leave_service.count_working_days(db, run.period_start, run.period_end, branch),
            active_start=active_start, active_end=active_end, unpaid_days=unpaid)
        if not res.lines:
            skipped.append({"employee": emp.full_name, "reason": ", ".join(res.exceptions) or "nothing payable"})
            continue

        tax, employer = ZERO, {}
        if tax_on:
            ytd_taxable, ytd_tax = _ytd(db, emp.id, ty, run.period_start)
            leaving = emp.exit_date is not None and emp.exit_date <= run.period_end
            current = [r for r in revisions if r.effective_from <= run.period_end] or revisions[:1]
            tax = pk.monthly_withholding(
                ty, ytd_taxable=ytd_taxable, ytd_tax=ytd_tax, current_taxable=engine.money(res.taxable_income),
                future_monthly_taxable=engine.regular_taxable(current[-1]),
                months_remaining=1 if leaving else pk.months_left(run.period_end))
            if tax > 0:
                res.lines.append(engine.LineResult("Income tax", "deduction", "income_tax", False, tax))
        if eobi_on:
            base = Decimal(str(cfg["eobi_wage_base"]))
            res.lines.append(engine.LineResult("EOBI (employee share)", "deduction", "eobi", False,
                                               engine.money(base * Decimal(str(cfg["eobi_employee_percent"])) / 100)))
            employer["EOBI (employer share)"] = str(engine.money(base * Decimal(str(cfg["eobi_employer_percent"])) / 100))

        claims = db.scalars(select(ExpenseClaim).where(
            ExpenseClaim.employee_id == emp.id, ExpenseClaim.status == "approved",
            ExpenseClaim.reimburse_via == "payroll", ExpenseClaim.payroll_run_id.is_(None)).with_for_update()).all()
        if claims:
            res.lines.append(engine.LineResult("Expense reimbursement", "earning", "expense", False,
                                               sum((c.approved_amount for c in claims), ZERO)))
            for c in claims:
                c.payroll_run_id = run.id
        due = db.scalars(select(LoanInstallment).join(Loan, Loan.id == LoanInstallment.loan_id).where(
            LoanInstallment.employee_id == emp.id, LoanInstallment.status == "due", Loan.status == "active",
            LoanInstallment.payroll_run_id.is_(None), LoanInstallment.due_date <= run.period_end)
                            .with_for_update(of=LoanInstallment)).all()
        if due:
            res.lines.append(engine.LineResult("Loan repayment", "deduction", "loan", False,
                                               sum((i.amount for i in due), ZERO)))
            for i in due:
                i.payroll_run_id = run.id
        engine.flag_negative(res)

        entry = PayrollEntry(tenant_id=tenant.id, run_id=run.id, employee_id=emp.id, gross=engine.money(res.gross),
                             deductions=engine.money(res.deductions), net=engine.money(res.net), unpaid_days=unpaid,
                             taxable_income=engine.money(res.taxable_income), income_tax=tax,
                             employer_contributions=employer, exceptions=res.exceptions)
        db.add(entry)
        db.flush()
        for ln in res.lines:
            db.add(PayrollLineItem(tenant_id=tenant.id, entry_id=entry.id, name=ln.name, kind=ln.kind,
                                   source=ln.source, taxable=ln.taxable, amount=ln.amount))
        totals[0] += entry.gross
        totals[1] += entry.deductions
        totals[2] += entry.net
        entries += 1
    run.total_gross, run.total_deductions, run.total_net = totals
    run.status, run.calculated_at = "calculated", utcnow()
    tenancy.record_audit(db, tenant_id=tenant.id, actor=actor, action="payroll.calculated",
                         entity_type="payroll_run", entity_id=run.id,
                         details={"entries": entries, "statutory": run.statutory_status})
    db.commit()
    return {"entries": entries, "skipped": skipped}


def exceptions_of(db: Session, run: PayrollRun) -> list[dict]:
    names = {e.id: e.full_name for e in db.scalars(select(Employee))}
    return [{"employee": names.get(e.employee_id), "exceptions": e.exceptions}
            for e in db.scalars(select(PayrollEntry).where(PayrollEntry.run_id == run.id)) if e.exceptions]


def approve_run(db: Session, *, tenant: Tenant, actor: uuid.UUID, run: PayrollRun) -> PayrollRun:
    _lock_finance(db, tenant, run)
    if run.status != "calculated":
        raise Conflict("Calculate the run before approving it", code="invalid_state")
    if run.created_by == actor and not tenant.settings.get("payroll_allow_self_approval", False):
        raise Forbidden("The person who created a payroll run cannot approve it", code="self_approval")
    blocking = exceptions_of(db, run)
    if blocking:
        raise Conflict("Resolve payroll exceptions before approving", code="unresolved_exceptions", details=blocking)
    run.status, run.approved_by, run.approved_at = "approved", actor, utcnow()
    tenancy.record_audit(db, tenant_id=tenant.id, actor=actor, action="payroll.approved", entity_type="payroll_run",
                         entity_id=run.id, details={"net": str(run.total_net)})
    db.commit()
    return run


def finalize_run(db: Session, *, tenant: Tenant, actor: uuid.UUID, run: PayrollRun) -> PayrollRun:
    _lock_finance(db, tenant, run)
    if run.status == "finalized":
        raise Conflict("This run is already finalized", code="already_finalized")
    if run.status != "approved":
        raise Conflict("Approve the run before finalizing it", code="invalid_state")
    run.status, run.finalized_by, run.finalized_at = "finalized", actor, utcnow()
    # Settle what this run paid or collected. Each item is tied to exactly one run, so it cannot be paid twice.
    loan_ids = set()
    for i in db.scalars(select(LoanInstallment).where(LoanInstallment.payroll_run_id == run.id,
                                                      LoanInstallment.status == "due")):
        i.status, i.method, i.paid_on = "paid", "payroll", run.period_end
        loan_ids.add(i.loan_id)
    db.flush()
    for loan in db.scalars(select(Loan).where(Loan.id.in_(loan_ids))) if loan_ids else []:
        if not db.scalar(select(LoanInstallment.id).where(LoanInstallment.loan_id == loan.id,
                                                          LoanInstallment.status == "due")):
            loan.status, loan.closed_at = "closed", utcnow()
    for c in db.scalars(select(ExpenseClaim).where(ExpenseClaim.payroll_run_id == run.id,
                                                   ExpenseClaim.status == "approved")):
        c.status, c.reimbursed_at = "reimbursed", utcnow()
    tenancy.record_audit(db, tenant_id=tenant.id, actor=actor, action="payroll.finalized", entity_type="payroll_run",
                         entity_id=run.id, details={"net": str(run.total_net)})
    for e in db.scalars(select(PayrollEntry).where(PayrollEntry.run_id == run.id)):
        emp = db.get(Employee, e.employee_id)
        notify_employee(db, emp, "payslip", "Your payslip is available",
                        f"Payslip for {run.period_start} to {run.period_end}", "/me/payslips",
                        dedupe_key=f"payslip:{run.id}")
    db.commit()
    return run


def delete_run(db: Session, *, tenant: Tenant, actor: uuid.UUID, run: PayrollRun) -> None:
    _lock_finance(db, tenant, run)
    if run.status in ("approved", "finalized"):
        raise Conflict("Approved or finalized runs cannot be deleted", code="run_locked")
    _release(db, run)
    tenancy.record_audit(db, tenant_id=tenant.id, actor=actor, action="payroll.run_deleted",
                         entity_type="payroll_run", entity_id=run.id)
    db.delete(run)
    db.commit()


def variance(db: Session, run: PayrollRun) -> list[dict]:
    prev = db.scalar(select(PayrollRun).where(PayrollRun.status == "finalized", PayrollRun.id != run.id,
                                              PayrollRun.period_end < run.period_start)
                     .order_by(PayrollRun.period_end.desc()))
    prev_net = {e.employee_id: e.net for e in db.scalars(select(PayrollEntry).where(
        PayrollEntry.run_id == prev.id))} if prev else {}
    names = {e.id: e.full_name for e in db.scalars(select(Employee))}
    out = []
    for e in db.scalars(select(PayrollEntry).where(PayrollEntry.run_id == run.id)):
        before = prev_net.get(e.employee_id)
        change = None if before in (None, 0) else (e.net - before) / before * 100
        out.append({"employee": names.get(e.employee_id), "net": e.net, "previous_net": before,
                    "change_percent": None if change is None else round(float(change), 1)})
    return sorted(out, key=lambda r: abs(r["change_percent"] or 0), reverse=True)


def get_entry_with_lines(db: Session, entry: PayrollEntry) -> list[PayrollLineItem]:
    return list(db.scalars(select(PayrollLineItem).where(PayrollLineItem.entry_id == entry.id)
                           .order_by(PayrollLineItem.kind.desc(), PayrollLineItem.name)))


def get_run(db: Session, run_id: uuid.UUID) -> PayrollRun:
    run = db.get(PayrollRun, run_id)
    if run is None:
        raise NotFound("Payroll run not found")
    return run
