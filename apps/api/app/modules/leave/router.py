from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden, NotFound
from app.db.session import get_db
from app.modules.employees import service as emp_service
from app.modules.employees.models import Employee
from app.modules.identity.deps import AuthContext, check_origin, get_tenant_ctx, require
from app.modules.leave import service
from app.modules.leave.models import LeaveLedgerEntry, LeaveRequest, LeaveType
from app.modules.tenancy import service as tenancy

router = APIRouter(prefix="/leave", tags=["leave"], dependencies=[Depends(check_origin)])


class LeaveTypeIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    days_per_year: Decimal = Field(ge=0, le=366)
    is_paid: bool = True
    allow_negative: bool = False
    allow_half_day: bool = True
    after_probation: bool = False
    carry_forward_max: Decimal = Field(default=Decimal("0"), ge=0, le=366)
    is_active: bool = True


class ApplyIn(BaseModel):
    leave_type_id: uuid.UUID
    start_date: date
    end_date: date
    half_day: bool = False
    reason: str | None = Field(default=None, max_length=1000)
    employee_id: uuid.UUID | None = None  # only honoured for leave.manage (HR files on behalf)


class DecisionIn(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=500)


class AdjustIn(BaseModel):
    employee_id: uuid.UUID
    leave_type_id: uuid.UUID
    days: Decimal = Field(ge=-366, le=366)
    note: str = Field(min_length=3, max_length=255)


def _me(db: Session, ctx: AuthContext) -> Employee | None:
    return emp_service.current_employee(db, ctx.membership.id if ctx.membership else None)


def _type(t: LeaveType) -> dict:
    return {"id": t.id, "name": t.name, "days_per_year": t.days_per_year, "is_paid": t.is_paid,
            "allow_negative": t.allow_negative, "allow_half_day": t.allow_half_day,
            "after_probation": t.after_probation, "carry_forward_max": t.carry_forward_max, "is_active": t.is_active}


def _req(r: LeaveRequest, emps: dict, types: dict) -> dict:
    e = emps.get(r.employee_id)
    return {"id": r.id, "employee_id": r.employee_id, "employee": e.full_name if e else None,
            "employee_code": e.employee_code if e else None, "leave_type_id": r.leave_type_id,
            "leave_type": types.get(r.leave_type_id), "start_date": r.start_date, "end_date": r.end_date,
            "half_day": r.half_day, "days": r.days, "reason": r.reason, "status": r.status,
            "decision_note": r.decision_note, "created_at": r.created_at}


@router.get("/types")
def list_types(ctx: AuthContext = Depends(require("org.read")), db: Session = Depends(get_db)):
    service.ensure_default_types(db, ctx.tenant.id)
    return [_type(t) for t in db.scalars(select(LeaveType).order_by(LeaveType.name))]


@router.post("/types", status_code=201)
def create_type(body: LeaveTypeIn, ctx: AuthContext = Depends(require("leave.manage")), db: Session = Depends(get_db)):
    if db.scalar(select(func.count()).select_from(LeaveType).where(func.lower(LeaveType.name) == body.name.lower())):
        raise Conflict("A leave type with this name exists", code="duplicate_name")
    t = LeaveType(tenant_id=ctx.tenant.id, **body.model_dump())
    db.add(t)
    tenancy.record_audit(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id, action="leave_type.created",
                         entity_type="leave_type", details={"name": t.name}, ip=ctx.ip)
    db.commit()
    return _type(t)


@router.put("/types/{type_id}")
def update_type(type_id: uuid.UUID, body: LeaveTypeIn, ctx: AuthContext = Depends(require("leave.manage")),
                db: Session = Depends(get_db)):
    t = db.get(LeaveType, type_id)
    if t is None:
        raise NotFound("Leave type not found")
    for k, v in body.model_dump().items():
        setattr(t, k, v)
    tenancy.record_audit(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id, action="leave_type.updated",
                         entity_type="leave_type", entity_id=t.id, ip=ctx.ip)
    db.commit()
    return _type(t)


@router.get("/balances")
def my_balances(employee_id: uuid.UUID | None = None, year: int | None = None,
                ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    me = _me(db, ctx)
    target = me.id if employee_id is None and me else employee_id
    if target is None:
        raise NotFound("No employee record is linked to your account")
    emp_service.assert_can_view(db, ctx.permissions, me, target)
    return service.balances(db, target, year)


@router.get("/ledger")
def ledger(employee_id: uuid.UUID | None = None, ctx: AuthContext = Depends(get_tenant_ctx),
           db: Session = Depends(get_db)):
    me = _me(db, ctx)
    target = me.id if employee_id is None and me else employee_id
    if target is None:
        raise NotFound("No employee record is linked to your account")
    emp_service.assert_can_view(db, ctx.permissions, me, target)
    names = {t.id: t.name for t in db.scalars(select(LeaveType))}
    rows = db.scalars(select(LeaveLedgerEntry).where(LeaveLedgerEntry.employee_id == target)
                      .order_by(LeaveLedgerEntry.created_at.desc()).limit(200))
    return [{"id": r.id, "leave_type": names.get(r.leave_type_id), "entry_type": r.entry_type, "days": r.days,
             "effective_date": r.effective_date, "note": r.note, "created_at": r.created_at} for r in rows]


@router.post("/requests", status_code=201)
def apply_leave(body: ApplyIn, ctx: AuthContext = Depends(require("leave.apply")), db: Session = Depends(get_db)):
    me = _me(db, ctx)
    if body.employee_id and (me is None or body.employee_id != me.id):
        if "leave.manage" not in ctx.permissions:
            raise Forbidden("Only HR can file leave for someone else", code="permission_denied")
        emp = emp_service.get_employee(db, body.employee_id)
    else:
        emp = me
    if emp is None:
        raise NotFound("No employee record is linked to your account")
    req = service.apply(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id, emp=emp, type_id=body.leave_type_id,
                        start=body.start_date, end=body.end_date, half_day=body.half_day, reason=body.reason)
    return _req(req, {emp.id: emp}, {t.id: t.name for t in db.scalars(select(LeaveType))})


@router.get("/requests")
def list_requests(scope: str = Query("mine", pattern="^(mine|team|all)$"), status: str | None = None,
                  employee_id: uuid.UUID | None = None,
                  ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    me = _me(db, ctx)
    stmt = select(LeaveRequest).order_by(LeaveRequest.created_at.desc())
    if scope == "all":
        if "leave.manage" not in ctx.permissions:
            raise Forbidden("You do not have permission to view all requests", code="permission_denied")
    elif scope == "team":
        if "leave.approve" not in ctx.permissions or me is None:
            raise Forbidden("You do not have permission to view team requests", code="permission_denied")
        ids = emp_service.team_ids(db, me.id) - {me.id}
        stmt = stmt.where(LeaveRequest.employee_id.in_(ids))
    else:
        if me is None:
            return []
        stmt = stmt.where(LeaveRequest.employee_id == me.id)
    if status:
        stmt = stmt.where(LeaveRequest.status == status)
    if employee_id:
        stmt = stmt.where(LeaveRequest.employee_id == employee_id)
    rows = db.scalars(stmt.limit(300)).all()
    emps = {e.id: e for e in db.scalars(select(Employee).where(Employee.id.in_({r.employee_id for r in rows})))}
    return [_req(r, emps, {t.id: t.name for t in db.scalars(select(LeaveType))}) for r in rows]


def _load(db: Session, request_id: uuid.UUID) -> LeaveRequest:
    r = db.get(LeaveRequest, request_id)
    if r is None:
        raise NotFound("Leave request not found")
    return r


@router.post("/requests/{request_id}/decision")
def decide(request_id: uuid.UUID, body: DecisionIn, ctx: AuthContext = Depends(require("leave.approve")),
           db: Session = Depends(get_db)):
    r = service.decide(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id, perms=ctx.permissions, me=_me(db, ctx),
                       req=_load(db, request_id), approve=body.approve, note=body.note)
    return {"id": r.id, "status": r.status}


@router.post("/requests/{request_id}/cancel")
def cancel(request_id: uuid.UUID, ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    r = service.cancel(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id, perms=ctx.permissions, me=_me(db, ctx),
                       req=_load(db, request_id))
    return {"id": r.id, "status": r.status}


@router.post("/grants/run")
def run_grants(year: int = Query(ge=2000, le=2100), ctx: AuthContext = Depends(require("leave.manage")),
               db: Session = Depends(get_db)):
    service.ensure_default_types(db, ctx.tenant.id)
    return {"entries_created": service.grant_year(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id, year=year)}


@router.post("/carry-forward")
def run_carry_forward(from_year: int = Query(ge=2000, le=2100), ctx: AuthContext = Depends(require("leave.manage")),
                      db: Session = Depends(get_db)):
    return {"entries_created": service.carry_forward(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id,
                                                      from_year=from_year)}


@router.post("/adjustments", status_code=201)
def adjust(body: AdjustIn, ctx: AuthContext = Depends(require("leave.manage")), db: Session = Depends(get_db)):
    emp = emp_service.get_employee(db, body.employee_id)
    if db.get(LeaveType, body.leave_type_id) is None:
        raise NotFound("Leave type not found")
    service._ledger(db, ctx.tenant.id, emp.id, body.leave_type_id, "adjustment", body.days, date.today(),
                    note=body.note, actor=ctx.identity.id)
    tenancy.record_audit(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id, action="leave.adjusted",
                         entity_type="employee", entity_id=emp.id, details={"days": str(body.days)}, ip=ctx.ip)
    db.commit()
    return {"ok": True}


@router.get("/calendar")
def calendar(month: str = Query(pattern=r"^\d{4}-\d{2}$"), ctx: AuthContext = Depends(get_tenant_ctx),
             db: Session = Depends(get_db)):
    """Pending and approved leave overlapping the month, for the employees the caller may see."""
    y, m = int(month[:4]), int(month[5:])
    first = date(y, m, 1)
    last = (date(y + (m == 12), (m % 12) + 1, 1)) - timedelta(days=1)
    allowed = emp_service.visible_ids(db, ctx.permissions, _me(db, ctx))
    stmt = select(LeaveRequest).where(LeaveRequest.status.in_(("pending", "approved")),
                                      LeaveRequest.start_date <= last, LeaveRequest.end_date >= first)
    if allowed is not None:
        stmt = stmt.where(LeaveRequest.employee_id.in_(allowed))
    rows = db.scalars(stmt).all()
    emps = {e.id: e for e in db.scalars(select(Employee).where(Employee.id.in_({r.employee_id for r in rows})))}
    types = {t.id: t.name for t in db.scalars(select(LeaveType))}
    return [_req(r, emps, types) for r in rows]
