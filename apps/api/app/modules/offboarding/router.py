from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import events
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.db.base import utcnow
from app.db.session import get_db
from app.modules.assets.models import Asset, AssetAssignment
from app.modules.common import audit, emp_map, serialize_financial_writes
from app.modules.employees import service as emp_service
from app.modules.employees.models import LIVE_STATUSES
from app.modules.expenses.models import ExpenseClaim
from app.modules.identity.deps import AuthContext, check_origin, require
from app.modules.identity.models import AuthSession
from app.modules.leave import service as leave_service
from app.modules.loans.models import Loan, LoanInstallment
from app.modules.notifications.service import notify_employee, notify_permission_holders
from app.modules.offboarding.models import DEFAULT_ITEMS, Offboarding, OffboardingItem
from app.modules.tenancy.models import MembershipRole, Role, TenantMembership

router = APIRouter(prefix="/offboarding", tags=["offboarding"],
                   dependencies=[Depends(check_origin), Depends(serialize_financial_writes)])
manage = require("employees.manage")
EVENT = {"resignation": "resignation", "termination": "termination", "retirement": "retirement"}


class StartIn(BaseModel):
    employee_id: uuid.UUID
    kind: str = Field(pattern="^(resignation|termination|retirement)$")
    notice_date: date
    last_working_day: date
    reason: str | None = Field(default=None, max_length=2000)


class Settlement(BaseModel):
    leave_encashment_days: Decimal = Field(default=Decimal("0"), ge=0, le=366)
    notice_pay: Decimal = Field(default=Decimal("0"), ge=-100000000, le=100000000)
    other_additions: Decimal = Field(default=Decimal("0"), ge=0, le=100000000)
    other_deductions: Decimal = Field(default=Decimal("0"), ge=0, le=100000000)
    remarks: str | None = Field(default=None, max_length=2000)


class PatchIn(BaseModel):
    exit_interview: str | None = Field(default=None, max_length=10000)
    settlement: Settlement | None = None
    last_working_day: date | None = None


class ItemIn(BaseModel):
    department: str = Field(min_length=2, max_length=40)
    title: str = Field(min_length=3, max_length=200)


class ItemPatch(BaseModel):
    done: bool


def _summary(o: Offboarding, emps: dict, items: list[OffboardingItem] | None = None) -> dict:
    e = emps.get(o.employee_id)
    out = {"id": o.id, "employee_id": o.employee_id, "employee": e.full_name if e else None,
           "employee_code": e.employee_code if e else None, "kind": o.kind, "notice_date": o.notice_date,
           "last_working_day": o.last_working_day, "reason": o.reason, "status": o.status,
           "completed_at": o.completed_at}
    if items is not None:
        out["items_done"], out["items_total"] = sum(i.done for i in items), len(items)
    return out


def _items(db: Session, off_id: uuid.UUID) -> list[OffboardingItem]:
    return list(db.scalars(select(OffboardingItem).where(OffboardingItem.offboarding_id == off_id)
                           .order_by(OffboardingItem.department, OffboardingItem.title)))


def _open_assets(db: Session, employee_id: uuid.UUID) -> list[dict]:
    rows = db.execute(select(AssetAssignment, Asset).join(Asset, Asset.id == AssetAssignment.asset_id).where(
        AssetAssignment.employee_id == employee_id, AssetAssignment.returned_on.is_(None))).all()
    return [{"asset_id": a.id, "name": a.name, "serial_number": a.serial_number, "assigned_on": r.assigned_on}
            for r, a in rows]


def _loan_balance(db: Session, employee_id: uuid.UUID) -> Decimal:
    rows = db.execute(select(LoanInstallment.amount).join(Loan, Loan.id == LoanInstallment.loan_id).where(
        LoanInstallment.employee_id == employee_id, LoanInstallment.status == "due", Loan.status == "active")).all()
    return sum((r[0] for r in rows), Decimal("0"))


@router.get("")
def list_all(ctx: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    rows = db.scalars(select(Offboarding).order_by(Offboarding.created_at.desc())).all()
    emps = emp_map(db, {r.employee_id for r in rows})
    return [_summary(o, emps, _items(db, o.id)) for o in rows]


@router.post("", status_code=201)
def start(body: StartIn, ctx: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    emp = emp_service.get_employee(db, body.employee_id)
    if emp.status not in LIVE_STATUSES:
        raise Conflict("This employee has already left", code="invalid_status")
    if body.last_working_day < body.notice_date:
        raise ValidationFailed("The last working day is before the notice date", code="bad_date")
    if db.scalar(select(Offboarding.id).where(Offboarding.employee_id == emp.id, Offboarding.status == "in_progress")):
        raise Conflict("An exit process is already open for this employee", code="already_open")
    o = Offboarding(tenant_id=ctx.tenant.id, employee_id=emp.id, started_by=ctx.identity.id, settlement={},
                    **body.model_dump(exclude={"employee_id"}))
    db.add(o)
    db.flush()
    for dept, title in DEFAULT_ITEMS:
        db.add(OffboardingItem(tenant_id=ctx.tenant.id, offboarding_id=o.id, department=dept, title=title))
    audit(db, ctx, "offboarding.started", "offboarding", o.id, {"employee_id": str(emp.id), "kind": body.kind})
    if emp.manager_id:
        notify_employee(db, db.get(emp_service.Employee, emp.manager_id), "offboarding",
                        f"Exit process opened for {emp.full_name}", f"Last working day: {body.last_working_day}",
                        "/offboarding", dedupe_key=f"offboarding-start:{o.id}")
    notify_permission_holders(db, ctx.tenant.id, "employees.manage", "offboarding",
                              f"Exit process opened for {emp.full_name}", f"Last working day: {body.last_working_day}",
                              "/offboarding", dedupe_key=f"offboarding-start:{o.id}",
                              exclude_identity_id=ctx.identity.id)
    db.commit()
    return _summary(o, {emp.id: emp}, _items(db, o.id))


def _get(db: Session, off_id: uuid.UUID) -> Offboarding:
    o = db.get(Offboarding, off_id)
    if o is None:
        raise NotFound("Exit process not found")
    return o


def _open(db: Session, off_id: uuid.UUID) -> Offboarding:
    o = _get(db, off_id)
    if o.status != "in_progress":
        raise Conflict("This exit process is closed", code="invalid_state")
    return o


@router.get("/{off_id}")
def detail(off_id: uuid.UUID, ctx: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    o = _get(db, off_id)
    items = _items(db, o.id)
    out = _summary(o, emp_map(db, {o.employee_id}), items)
    pending_expenses = db.scalars(select(ExpenseClaim).where(
        ExpenseClaim.employee_id == o.employee_id,
        ExpenseClaim.status.in_(("submitted", "manager_approved", "approved")))).all()
    out.update({
        "exit_interview": o.exit_interview, "settlement": o.settlement or {},
        "items": [{"id": i.id, "department": i.department, "title": i.title, "done": i.done} for i in items],
        "open_assets": _open_assets(db, o.employee_id),
        "loan_balance": _loan_balance(db, o.employee_id),
        "pending_expense_claims": len(pending_expenses),
        "approved_unpaid_expenses": sum((c.approved_amount or Decimal("0") for c in pending_expenses
                                         if c.status == "approved"), Decimal("0")),
        "leave_balances": [b for b in leave_service.balances(db, o.employee_id, o.last_working_day.year)
                           if b["entitled"] > 0],
    })
    return out


@router.patch("/{off_id}")
def patch(off_id: uuid.UUID, body: PatchIn, ctx: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    o = _open(db, off_id)
    if body.exit_interview is not None:
        o.exit_interview = body.exit_interview
    if body.settlement is not None:
        o.settlement = body.settlement.model_dump(mode="json")
    if body.last_working_day is not None:
        if body.last_working_day < o.notice_date:
            raise ValidationFailed("The last working day is before the notice date", code="bad_date")
        o.last_working_day = body.last_working_day
    audit(db, ctx, "offboarding.updated", "offboarding", o.id)
    db.commit()
    return {"ok": True}


@router.post("/{off_id}/items", status_code=201)
def add_item(off_id: uuid.UUID, body: ItemIn, ctx: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    o = _open(db, off_id)
    i = OffboardingItem(tenant_id=ctx.tenant.id, offboarding_id=o.id, **body.model_dump())
    db.add(i)
    db.commit()
    return {"id": i.id}


@router.patch("/{off_id}/items/{item_id}")
def toggle_item(off_id: uuid.UUID, item_id: uuid.UUID, body: ItemPatch, ctx: AuthContext = Depends(manage),
                db: Session = Depends(get_db)):
    o = _open(db, off_id)
    i = db.scalar(select(OffboardingItem).where(OffboardingItem.id == item_id, OffboardingItem.offboarding_id == o.id))
    if i is None:
        raise NotFound("Checklist item not found")
    i.done, i.done_by, i.done_at = body.done, (ctx.identity.id if body.done else None), (utcnow() if body.done else None)
    db.commit()
    return {"id": i.id, "done": i.done}


@router.post("/{off_id}/cancel")
def cancel(off_id: uuid.UUID, ctx: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    o = _open(db, off_id)
    o.status = "cancelled"
    audit(db, ctx, "offboarding.cancelled", "offboarding", o.id)
    db.commit()
    return {"id": o.id, "status": o.status}


@router.post("/{off_id}/complete")
def complete(off_id: uuid.UUID, ctx: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    """Closes the exit: every clearance item done, assets back, loans cleared. Then the employee record is marked as
    left on the last working day and their access to this organization is revoked."""
    o = _open(db, off_id)
    blockers = []
    if any(not i.done for i in _items(db, o.id)):
        blockers.append("clearance items are still open")
    if _open_assets(db, o.employee_id):
        blockers.append("company assets have not been returned")
    if _loan_balance(db, o.employee_id) > 0:
        blockers.append("a loan balance is outstanding")
    if blockers:
        raise Conflict("Cannot complete the exit: " + ", ".join(blockers), code="clearance_incomplete", details=blockers)
    emp = emp_service.get_employee(db, o.employee_id)
    membership_id = emp.membership_id
    if membership_id and db.scalar(select(MembershipRole.id).join(Role, Role.id == MembershipRole.role_id).where(
            MembershipRole.membership_id == membership_id, Role.key == "owner")):
        raise Conflict("Transfer ownership and remove the owner role before completing this exit.", code="owner_exit")
    emp_service.record_lifecycle(db, tenant=ctx.tenant, actor=ctx.identity.id, emp=emp, event_type=EVENT[o.kind],
                                 effective_date=o.last_working_day, details={"offboarding_id": str(o.id)}, ip=ctx.ip,
                                 commit=False)
    if membership_id is not None:
        m = db.get(TenantMembership, membership_id)
        if m is not None and m.tenant_id == ctx.tenant.id:
            m.status = "removed"
            db.execute(update(AuthSession).where(AuthSession.identity_id == m.identity_id,
                                                 AuthSession.active_tenant_id == ctx.tenant.id,
                                                 AuthSession.revoked_at.is_(None)).values(revoked_at=utcnow()))
    o.status, o.completed_at = "completed", utcnow()
    audit(db, ctx, "offboarding.completed", "offboarding", o.id, {"access_revoked": membership_id is not None})
    db.commit()
    events.publish(f"employee.{EVENT[o.kind]}", {"tenant_id": ctx.tenant.id, "employee_id": emp.id})
    return {"id": o.id, "status": o.status, "access_revoked": membership_id is not None}
