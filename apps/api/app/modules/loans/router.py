from __future__ import annotations

import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.db.base import utcnow
from app.db.session import get_db
from app.modules.common import audit, emp_map, me_of, need_any, need_me, serialize_financial_writes
from app.modules.employees import service as emp_service
from app.modules.employees.models import LIVE_STATUSES
from app.modules.identity.deps import AuthContext, check_origin, get_tenant_ctx, require
from app.modules.loans.models import Loan, LoanInstallment
from app.modules.notifications.service import notify_employee, notify_permission_holders

router = APIRouter(prefix="/loans", tags=["loans"],
                   dependencies=[Depends(check_origin), Depends(serialize_financial_writes)])
CENT = Decimal("0.01")


class LoanIn(BaseModel):
    kind: str = Field(pattern="^(loan|advance)$")
    principal: Decimal = Field(gt=0, le=Decimal("100000000"))
    installments: int = Field(ge=1, le=60)
    reason: str | None = Field(default=None, max_length=1000)


class DecisionIn(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=500)


class DisburseIn(BaseModel):
    disbursed_on: date
    first_due_month: str = Field(pattern=r"^\d{4}-\d{2}$")


class RepayIn(BaseModel):
    installment_ids: list[uuid.UUID] = Field(default_factory=list, max_length=60)
    settle_all: bool = False


def schedule(principal: Decimal, n: int, first: date) -> list[tuple[int, date, Decimal]]:
    """Equal monthly installments due on the first of each month. The last one absorbs the rounding remainder."""
    each = (principal / n).quantize(CENT, rounding=ROUND_HALF_UP)
    out = []
    for i in range(n):
        month = first.month - 1 + i
        due = date(first.year + month // 12, month % 12 + 1, 1)
        out.append((i + 1, due, each if i < n - 1 else principal - each * (n - 1)))
    return out


def outstanding(db: Session, loan_id: uuid.UUID) -> Decimal:
    v = db.scalar(select(func.coalesce(func.sum(LoanInstallment.amount), 0)).where(
        LoanInstallment.loan_id == loan_id, LoanInstallment.status == "due"))
    return Decimal(str(v))


def close_if_repaid(db: Session, loan: Loan) -> None:
    db.flush()
    if loan.status == "active" and not db.scalar(select(LoanInstallment.id).where(
            LoanInstallment.loan_id == loan.id, LoanInstallment.status == "due")):
        loan.status, loan.closed_at = "closed", utcnow()


def _loan(loan: Loan, emps: dict, db: Session, detail: bool = False) -> dict:
    e = emps.get(loan.employee_id)
    out = {"id": loan.id, "employee_id": loan.employee_id, "employee": e.full_name if e else None, "kind": loan.kind,
           "principal": loan.principal, "installments": loan.installments, "reason": loan.reason,
           "status": loan.status, "decision_note": loan.decision_note, "disbursed_on": loan.disbursed_on,
           "outstanding": outstanding(db, loan.id) if loan.status in ("active", "closed") else None,
           "created_at": loan.created_at}
    if detail:
        out["schedule"] = [{"id": i.id, "seq": i.seq, "due_date": i.due_date, "amount": i.amount, "status": i.status,
                            "method": i.method, "paid_on": i.paid_on, "in_payroll": i.payroll_run_id is not None}
                           for i in db.scalars(select(LoanInstallment).where(LoanInstallment.loan_id == loan.id)
                                               .order_by(LoanInstallment.seq))]
    return out


@router.post("", status_code=201)
def request_loan(body: LoanIn, ctx: AuthContext = Depends(require("loans.request")), db: Session = Depends(get_db)):
    me = need_me(db, ctx)
    if me.status not in LIVE_STATUSES or me.status == "suspended":
        raise Conflict("You cannot request a loan in your current employment status", code="invalid_status")
    if body.kind == "advance" and body.installments > 3:
        raise ValidationFailed("A salary advance is repaid in at most 3 installments", code="advance_too_long")
    if db.scalar(select(Loan.id).where(Loan.employee_id == me.id, Loan.kind == body.kind,
                                       Loan.status.in_(("requested", "approved", "active")))):
        raise Conflict(f"You already have an open {body.kind}", code="open_loan_exists")
    loan = Loan(tenant_id=ctx.tenant.id, employee_id=me.id, **body.model_dump())
    db.add(loan)
    db.flush()
    audit(db, ctx, "loan.requested", "loan", loan.id, {"principal": str(body.principal), "kind": body.kind})
    notify_permission_holders(db, ctx.tenant.id, "loans.manage", "loan",
                              f"{body.kind.capitalize()} request from {me.full_name}",
                              f"Amount: {body.principal}", f"/inbox/loan/{loan.id}", dedupe_key=f"loan-request:{loan.id}",
                              exclude_identity_id=ctx.identity.id)
    db.commit()
    return _loan(loan, {me.id: me}, db)


@router.get("")
def list_loans(scope: str = Query("mine", pattern="^(mine|all)$"), status: str | None = None,
               employee_id: uuid.UUID | None = None,
               ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    me = me_of(db, ctx)
    stmt = select(Loan).order_by(Loan.created_at.desc()).limit(300)
    if scope == "all":
        need_any(ctx, "loans.manage")
    else:
        if me is None:
            return []
        stmt = stmt.where(Loan.employee_id == me.id)
    if status:
        stmt = stmt.where(Loan.status == status)
    if employee_id:
        stmt = stmt.where(Loan.employee_id == employee_id)
    rows = db.scalars(stmt).all()
    emps = emp_map(db, {r.employee_id for r in rows})
    return [_loan(r, emps, db) for r in rows]


def _load(db: Session, ctx: AuthContext, loan_id: uuid.UUID) -> Loan:
    loan = db.get(Loan, loan_id)
    me = me_of(db, ctx)
    if loan is None or not ("loans.manage" in ctx.permissions or (me is not None and me.id == loan.employee_id)):
        raise NotFound("Loan not found")
    return loan


@router.get("/{loan_id}")
def get_loan(loan_id: uuid.UUID, ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    loan = _load(db, ctx, loan_id)
    return _loan(loan, emp_map(db, {loan.employee_id}), db, detail=True)


@router.post("/{loan_id}/decision")
def decide(loan_id: uuid.UUID, body: DecisionIn, ctx: AuthContext = Depends(require("loans.manage")),
           db: Session = Depends(get_db)):
    loan, me = _load(db, ctx, loan_id), me_of(db, ctx)
    if me is not None and me.id == loan.employee_id:
        raise Forbidden("You cannot approve your own loan", code="self_approval")
    if loan.status != "requested":
        raise Conflict("This request has already been decided", code="already_decided")
    loan.status = "approved" if body.approve else "rejected"
    loan.decided_by, loan.decision_note = ctx.identity.id, body.note
    notify_employee(db, emp_service.get_employee(db, loan.employee_id), "loan",
                    f"Your {loan.kind} request was {loan.status}", body.note, "/me/loans")
    audit(db, ctx, f"loan.{loan.status}", "loan", loan.id)
    db.commit()
    return {"id": loan.id, "status": loan.status}


@router.post("/{loan_id}/disburse")
def disburse(loan_id: uuid.UUID, body: DisburseIn, ctx: AuthContext = Depends(require("loans.manage")),
             db: Session = Depends(get_db)):
    loan = _load(db, ctx, loan_id)
    if loan.status != "approved":
        raise Conflict("Only approved loans can be disbursed", code="invalid_state")
    first = date(int(body.first_due_month[:4]), int(body.first_due_month[5:]), 1)
    if first < body.disbursed_on.replace(day=1):
        raise ValidationFailed("The first installment cannot be due before the disbursement month", code="bad_schedule")
    for seq, due, amount in schedule(loan.principal, loan.installments, first):
        db.add(LoanInstallment(tenant_id=ctx.tenant.id, loan_id=loan.id, employee_id=loan.employee_id, seq=seq,
                               due_date=due, amount=amount))
    loan.status, loan.disbursed_on = "active", body.disbursed_on
    notify_employee(db, emp_service.get_employee(db, loan.employee_id), "loan",
                    f"Your {loan.kind} has been disbursed", f"Amount: {loan.principal}", "/me/loans")
    audit(db, ctx, "loan.disbursed", "loan", loan.id, {"first_due": first.isoformat()})
    db.commit()
    return _loan(loan, emp_map(db, {loan.employee_id}), db, detail=True)


@router.post("/{loan_id}/repay")
def repay(loan_id: uuid.UUID, body: RepayIn, ctx: AuthContext = Depends(require("loans.manage")),
          db: Session = Depends(get_db)):
    """Records a repayment made outside payroll, for chosen installments or the whole balance."""
    loan = _load(db, ctx, loan_id)
    if loan.status != "active":
        raise Conflict("This loan is not active", code="invalid_state")
    stmt = select(LoanInstallment).where(LoanInstallment.loan_id == loan.id, LoanInstallment.status == "due")
    if not body.settle_all:
        if not body.installment_ids:
            raise ValidationFailed("Choose installments or settle the whole balance", code="nothing_selected")
        stmt = stmt.where(LoanInstallment.id.in_(body.installment_ids))
    rows = db.scalars(stmt).all()
    if not rows:
        raise Conflict("Nothing is due on the selected installments", code="nothing_due")
    if any(i.payroll_run_id for i in rows):
        raise Conflict("An installment is already included in a payroll run. Finalize or delete that run first.",
                       code="in_payroll")
    for i in rows:
        i.status, i.method, i.paid_on = "paid", "manual", date.today()
    close_if_repaid(db, loan)
    notify_employee(db, emp_service.get_employee(db, loan.employee_id), "loan",
                    f"{loan.kind.capitalize()} repayment recorded", f"{len(rows)} installment(s) paid.", "/me/loans")
    audit(db, ctx, "loan.repaid_manually", "loan", loan.id, {"installments": len(rows)})
    db.commit()
    return _loan(loan, emp_map(db, {loan.employee_id}), db, detail=True)


@router.post("/{loan_id}/cancel")
def cancel(loan_id: uuid.UUID, ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    loan = _load(db, ctx, loan_id)
    if loan.status not in ("requested", "approved"):
        raise Conflict("This loan can no longer be cancelled", code="invalid_state")
    loan.status = "cancelled"
    db.commit()
    return {"id": loan.id, "status": loan.status}
