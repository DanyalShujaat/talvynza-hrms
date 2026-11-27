from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.db.base import utcnow
from app.db.session import get_db
from app.modules.attendance import service
from app.modules.attendance.location import PunchLocation, branch_premises, validate_location
from app.modules.attendance.models import (
    AttendanceAdjustment,
    AttendanceDaily,
    AttendancePolicy,
    Shift,
    ShiftAssignment,
)
from app.modules.employees import service as emp_service
from app.modules.employees.models import LIVE_STATUSES, Employee
from app.modules.identity.deps import AuthContext, check_origin, get_tenant_ctx, require
from app.modules.leave.models import LeaveRequest
from app.modules.notifications.service import notify_employee
from app.modules.organization.models import Branch, Department
from app.modules.tenancy import service as tenancy

router = APIRouter(prefix="/attendance", tags=["attendance"], dependencies=[Depends(check_origin)])
shifts_router = APIRouter(prefix="/shifts", tags=["shifts"], dependencies=[Depends(check_origin)])


class PolicyIn(BaseModel):
    grace_minutes: int = Field(ge=0, le=120)
    late_mode: str = Field(pattern="^(full|grace_exempt)$")
    overtime_threshold_minutes: int = Field(ge=0, le=600)
    weekend_days: list[int] = Field(max_length=6)
    default_start: time
    default_end: time
    default_break_minutes: int = Field(ge=0, le=240)


class ManualIn(BaseModel):
    employee_id: uuid.UUID
    kind: str = Field(pattern="^(in|out)$")
    occurred_at: datetime


class AdjustmentIn(BaseModel):
    work_date: date
    in_time: str | None = Field(default=None, pattern=r"^\d{1,2}:\d{2}$")
    out_time: str | None = Field(default=None, pattern=r"^\d{1,2}:\d{2}$")
    reason: str = Field(min_length=3, max_length=500)


class DecisionIn(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=500)


class ShiftIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    start_time: time
    end_time: time
    break_minutes: int = Field(default=0, ge=0, le=240)
    grace_minutes: int | None = Field(default=None, ge=0, le=120)
    color: str | None = Field(default=None, max_length=9)


class AssignIn(BaseModel):
    shift_id: uuid.UUID
    employee_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    department_id: uuid.UUID | None = None
    effective_from: date


class AttendanceAccessIn(BaseModel):
    channel: Literal["web", "mobile", "premises"] = "web"
    enabled: bool
    branch_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    employee_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    all_employees: bool = False


class MobilePunchIn(BaseModel):
    location: PunchLocation | None = None


ACCESS_COLUMNS = {
    "web": Employee.attendance_enabled,
    "mobile": Employee.mobile_attendance_enabled,
    "premises": Employee.premises_attendance_enabled,
}


def _channels(emp: Employee) -> dict[str, bool]:
    return {channel: getattr(emp, column.key) for channel, column in ACCESS_COLUMNS.items()}


def _me(db: Session, ctx: AuthContext) -> Employee | None:
    return emp_service.current_employee(db, ctx.membership.id if ctx.membership else None)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _daily(r: AttendanceDaily) -> dict:
    return {"work_date": r.work_date, "status": r.status, "first_in": _iso(r.first_in), "last_out": _iso(r.last_out),
            "worked_minutes": r.worked_minutes, "late_minutes": r.late_minutes,
            "early_leave_minutes": r.early_leave_minutes, "overtime_minutes": r.overtime_minutes}


# ------------------------------------------------------------------ policy
@router.get("/policy")
def get_policy(ctx: AuthContext = Depends(require("org.read")), db: Session = Depends(get_db)):
    p = service.get_policy(db, ctx.tenant.id)
    db.commit()
    return {"grace_minutes": p.grace_minutes, "late_mode": p.late_mode,
            "overtime_threshold_minutes": p.overtime_threshold_minutes, "weekend_days": p.weekend_days,
            "default_start": p.default_start.strftime("%H:%M"), "default_end": p.default_end.strftime("%H:%M"),
            "default_break_minutes": p.default_break_minutes}


@router.put("/policy")
def put_policy(body: PolicyIn, ctx: AuthContext = Depends(require("attendance.manage")),
               db: Session = Depends(get_db)):
    if any(d < 0 or d > 6 for d in body.weekend_days):
        raise ValidationFailed("weekend_days must be 0 (Monday) to 6 (Sunday)")
    p = service.get_policy(db, ctx.tenant.id)
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    tenancy.record_audit(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id, action="attendance.policy_updated",
                         entity_type="attendance_policy", details=body.model_dump(mode="json"), ip=ctx.ip)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ self service
@router.get("/employees/{employee_id}/settings")
def employee_settings(employee_id: uuid.UUID, ctx: AuthContext = Depends(get_tenant_ctx),
                      db: Session = Depends(get_db)):
    emp_service.assert_can_view(db, ctx.permissions, _me(db, ctx), employee_id)
    emp = emp_service.get_employee(db, employee_id)
    on = utcnow().astimezone(service.tz_of(ctx.tenant)).date()
    policy = db.scalar(select(AttendancePolicy))
    assignment = service.current_shift_assignment(db, employee_id, on)
    shift = db.get(Shift, assignment.shift_id) if assignment else None
    start = shift.start_time if shift else policy.default_start if policy else None
    end = shift.end_time if shift else policy.default_end if policy else None
    return {
        "attendance_enabled": emp.attendance_enabled,
        "channels": _channels(emp),
        "biometric_id": emp.bio_id,
        "branch_id": emp.branch_id,
        "location_required": bool(branch_premises(db, emp)),
        "shift": shift.name if shift else None,
        "effective_from": assignment.effective_from if assignment else None,
        "start": start.strftime("%H:%M") if start else None,
        "end": end.strftime("%H:%M") if end else None,
        "break_minutes": shift.break_minutes if shift else policy.default_break_minutes if policy else None,
        "grace_minutes": shift.grace_minutes if shift and shift.grace_minutes is not None
        else policy.grace_minutes if policy else None,
    }


@router.get("/today")
def today(ctx: AuthContext = Depends(require("attendance.read_own")), db: Session = Depends(get_db)):
    me = _me(db, ctx)
    if me is None:
        raise NotFound("No employee record is linked to your account")
    now = utcnow()
    wd = service.work_date_for(db, ctx.tenant, me, now)
    row = service.recompute(db, ctx.tenant, me, wd)
    db.commit()
    return {"work_date": wd, "state": service.open_state(db, ctx.tenant, me, now), "summary": _daily(row),
            "channels": _channels(me), "location_required": bool(branch_premises(db, me)),
            "biometric_ready": bool(me.branch_id and me.bio_id), "can_punch": me.status in ("active", "probation")}


def _self_punch(db: Session, ctx: AuthContext, kind: str, channel: Literal["web", "mobile"],
                location: PunchLocation | None = None):
    me = _me(db, ctx)
    if me is not None:
        # Serialize with other punches and admin access changes for this employee.
        me = db.scalar(select(Employee).where(Employee.id == me.id, Employee.deleted_at.is_(None))
                       .with_for_update().execution_options(populate_existing=True))
    if kind == "in" and (me is None or me.status not in LIVE_STATUSES or me.status == "suspended"):
        raise Forbidden("Your employee record cannot record attendance", code="not_allowed")
    if me is None:
        raise NotFound("No employee record is linked to your account")
    if not _channels(me)[channel]:
        raise Forbidden(f"{channel.capitalize()} attendance is disabled for your employee record", code="attendance_disabled")
    premises = branch_premises(db, me)
    if channel == "web" and premises:
        raise Forbidden("Use mobile or a branch biometric device to punch at your assigned premises",
                        code="web_blocked_by_premises")
    if channel == "mobile":
        validate_location(premises, location)
    return _daily(service.check(db, ctx.tenant, me, kind, ctx.identity.id, source=channel))


@router.post("/check-in")
def check_in(ctx: AuthContext = Depends(require("attendance.record_own")),
             db: Session = Depends(get_db)):
    return _self_punch(db, ctx, "in", "web")


@router.post("/check-out")
def check_out(ctx: AuthContext = Depends(require("attendance.record_own")),
              db: Session = Depends(get_db)):
    return _self_punch(db, ctx, "out", "web")


@router.post("/mobile/check-in")
def mobile_check_in(body: MobilePunchIn | None = None, ctx: AuthContext = Depends(require("attendance.record_own")),
                    db: Session = Depends(get_db)):
    return _self_punch(db, ctx, "in", "mobile", body.location if body else None)


@router.post("/mobile/check-out")
def mobile_check_out(body: MobilePunchIn | None = None, ctx: AuthContext = Depends(require("attendance.record_own")),
                     db: Session = Depends(get_db)):
    return _self_punch(db, ctx, "out", "mobile", body.location if body else None)


@router.get("/me")
def my_month(month: str = Query(pattern=r"^\d{4}-\d{2}$"), employee_id: uuid.UUID | None = None,
             ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    me = _me(db, ctx)
    target = employee_id or (me.id if me else None)
    if target is None:
        raise NotFound("No employee record is linked to your account")
    emp_service.assert_can_view(db, ctx.permissions, me, target)
    y, m = int(month[:4]), int(month[5:])
    try:
        first = date(y, m, 1)
        last = date(y + (m == 12), (m % 12) + 1, 1) - timedelta(days=1)
    except ValueError:
        raise ValidationFailed("Choose a valid report month", code="invalid_month") from None
    rows = db.scalars(select(AttendanceDaily).where(
        AttendanceDaily.employee_id == target, AttendanceDaily.work_date >= first,
        AttendanceDaily.work_date <= last).order_by(AttendanceDaily.work_date)).all()
    return {"month": month, "days": [_daily(r) for r in rows],
            "totals": {"worked_minutes": sum(r.worked_minutes for r in rows),
                       "late_minutes": sum(r.late_minutes for r in rows),
                       "overtime_minutes": sum(r.overtime_minutes for r in rows),
                       "present_days": sum(1 for r in rows if r.status in ("present", "incomplete")),
                       "late_days": sum(1 for r in rows if r.late_minutes > 0)}}


# ------------------------------------------------------------------ team / HR views
def _access_scope(db: Session, branch_id: uuid.UUID | None, department_id: uuid.UUID | None,
                  employee_ids: list[uuid.UUID], all_employees: bool):
    filtered = bool(branch_id or department_id or employee_ids)
    if filtered == all_employees:
        raise ValidationFailed("Choose a branch, department, or employees, or explicitly select the whole organization")
    filters = [Employee.deleted_at.is_(None), Employee.status.in_(LIVE_STATUSES)]
    for model, value, column in ((Branch, branch_id, Employee.branch_id),
                                 (Department, department_id, Employee.department_id)):
        if value is not None:
            if db.get(model, value) is None:
                raise NotFound(f"{model.__name__} not found")
            filters.append(column == value)
    if employee_ids:
        filters.append(Employee.id.in_(employee_ids))
    return filters


@router.get("/access")
def preview_access(branch_id: uuid.UUID | None = None, department_id: uuid.UUID | None = None,
                   channel: Literal["web", "mobile", "premises"] = "web",
                   all_employees: bool = False, ctx: AuthContext = Depends(require("attendance.manage")),
                   db: Session = Depends(get_db)):
    filters = _access_scope(db, branch_id, department_id, [], all_employees)
    column = ACCESS_COLUMNS[channel]
    counts = dict(db.execute(select(column, func.count()).where(*filters).group_by(column)).all())
    rows = db.scalars(select(Employee).where(*filters).order_by(Employee.first_name, Employee.last_name, Employee.id)
                      .limit(12))
    return {"total": sum(counts.values()), "enabled": counts.get(True, 0),
            "sample": [{"id": e.id, "name": e.full_name, "code": e.employee_code, "enabled": _channels(e)[channel]}
                       for e in rows]}


@router.patch("/access")
def update_access(body: AttendanceAccessIn, ctx: AuthContext = Depends(require("attendance.manage")),
                  db: Session = Depends(get_db)):
    filters = _access_scope(db, body.branch_id, body.department_id, body.employee_ids, body.all_employees)
    matched = db.scalar(select(func.count()).select_from(Employee).where(*filters)) or 0
    if not matched or (body.employee_ids and matched != len(set(body.employee_ids))):
        raise NotFound("One or more eligible employees could not be found")
    column = ACCESS_COLUMNS[body.channel]
    result = db.execute(update(Employee).where(*filters, column != body.enabled).values({column: body.enabled}))
    changed = result.rowcount
    tenancy.record_audit(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id, action="attendance.access_updated",
                         entity_type="employee", details={**body.model_dump(mode="json"), "changed": changed}, ip=ctx.ip)
    db.commit()
    return {"matched": matched, "changed": changed}


@router.get("/daily")
def daily(on: date = Query(alias="date"), branch_id: uuid.UUID | None = None, department_id: uuid.UUID | None = None,
          page: int = Query(default=1, ge=1), paginated: bool = False,
          ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    if "attendance.manage" not in ctx.permissions and "attendance.approve" not in ctx.permissions:
        raise Forbidden("You do not have permission to view team attendance", code="permission_denied")
    me = _me(db, ctx)
    allowed = None if "attendance.manage" in ctx.permissions else (
        emp_service.team_ids(db, me.id) if me else set())
    rows_e, total = emp_service.list_employees(db, allowed=allowed, branch_id=branch_id, department_id=department_id,
                                               status="active", page=page, page_size=100)
    names = emp_service.name_maps(db)
    daily_rows = {r.employee_id: r for r in db.scalars(select(AttendanceDaily).where(
        AttendanceDaily.work_date == on, AttendanceDaily.employee_id.in_([e.id for e in rows_e])))}
    policy = service.get_policy(db, ctx.tenant.id)
    out = []
    for e in rows_e:
        r = daily_rows.get(e.id)
        if r is not None:
            item = _daily(r)
        else:
            status = service.non_working_reason(db, policy, e, on) or ("leave" if service.on_leave(db, e.id, on)
                                                                       else ("absent" if on <= date.today()
                                                                             else "scheduled"))
            item = {"work_date": on, "status": status, "first_in": None, "last_out": None, "worked_minutes": 0,
                    "late_minutes": 0, "early_leave_minutes": 0, "overtime_minutes": 0}
        item.update({"employee_id": e.id, "employee_code": e.employee_code, "full_name": e.full_name,
                     "department": names["department"].get(e.department_id)})
        out.append(item)
    db.commit()
    return {"items": out, "total": total, "page_size": 100} if paginated else out


@router.post("/manual", status_code=201)
def manual(body: ManualIn, ctx: AuthContext = Depends(require("attendance.manage")), db: Session = Depends(get_db)):
    emp = emp_service.get_employee(db, body.employee_id)
    at = body.occurred_at
    if at.tzinfo is None:
        raise ValidationFailed("occurred_at needs a time zone offset", code="naive_datetime")
    row = service.punch(db, ctx.tenant, emp, body.kind, at.replace(microsecond=0), source="manual",
                        actor=ctx.identity.id)
    tenancy.record_audit(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id, action="attendance.manual_entry",
                         entity_type="employee", entity_id=emp.id, details={"kind": body.kind, "at": at.isoformat()},
                         ip=ctx.ip)
    db.commit()
    return _daily(row)


@router.post("/import")
def import_csv(file: UploadFile = File(...), branch_id: uuid.UUID | None = Form(default=None),
               ctx: AuthContext = Depends(require("attendance.manage")),
               db: Session = Depends(get_db)):
    data = file.file.read(5 * 1024 * 1024 + 1)
    if len(data) > 5 * 1024 * 1024:
        raise ValidationFailed("File is larger than 5 MB", code="file_too_large")
    if branch_id is not None and db.get(Branch, branch_id) is None:
        raise NotFound("Branch not found")
    return service.import_punches(db, ctx.tenant, ctx.identity.id, data, branch_id=branch_id)


# ------------------------------------------------------------------ corrections
def _adj(a: AttendanceAdjustment, emps: dict) -> dict:
    e = emps.get(a.employee_id)
    return {"id": a.id, "employee_id": a.employee_id, "employee": e.full_name if e else None,
            "work_date": a.work_date, "requested_in": _iso(a.requested_in), "requested_out": _iso(a.requested_out),
            "reason": a.reason, "status": a.status, "review_note": a.review_note, "created_at": a.created_at}


@router.post("/adjustments", status_code=201)
def create_adjustment(body: AdjustmentIn, ctx: AuthContext = Depends(require("attendance.record_own")),
                      db: Session = Depends(get_db)):
    me = _me(db, ctx)
    if me is None:
        raise NotFound("No employee record is linked to your account")
    a = service.request_adjustment(db, ctx.tenant, me, ctx.identity.id, body.work_date, body.in_time,
                                   body.out_time, body.reason)
    return _adj(a, {me.id: me})


@router.get("/adjustments")
def list_adjustments(scope: str = Query("mine", pattern="^(mine|team|all)$"), status: str | None = None,
                     ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    me = _me(db, ctx)
    stmt = select(AttendanceAdjustment).order_by(AttendanceAdjustment.created_at.desc()).limit(300)
    if scope == "all":
        if "attendance.manage" not in ctx.permissions:
            raise Forbidden("You do not have permission", code="permission_denied")
    elif scope == "team":
        if "attendance.approve" not in ctx.permissions or me is None:
            raise Forbidden("You do not have permission", code="permission_denied")
        stmt = stmt.where(AttendanceAdjustment.employee_id.in_(emp_service.team_ids(db, me.id) - {me.id}))
    else:
        if me is None:
            return []
        stmt = stmt.where(AttendanceAdjustment.employee_id == me.id)
    if status:
        stmt = stmt.where(AttendanceAdjustment.status == status)
    rows = db.scalars(stmt).all()
    emps = {e.id: e for e in db.scalars(select(Employee).where(Employee.id.in_({r.employee_id for r in rows})))}
    return [_adj(r, emps) for r in rows]


@router.post("/adjustments/{adjustment_id}/decision")
def decide_adjustment(adjustment_id: uuid.UUID, body: DecisionIn,
                      ctx: AuthContext = Depends(require("attendance.approve")), db: Session = Depends(get_db)):
    adj = db.get(AttendanceAdjustment, adjustment_id)
    if adj is None:
        raise NotFound("Request not found")
    a = service.decide_adjustment(db, ctx.tenant, ctx.identity.id, ctx.permissions, _me(db, ctx), adj, body.approve,
                                  body.note)
    return {"id": a.id, "status": a.status}


# ------------------------------------------------------------------ shifts
def _shift(s: Shift) -> dict:
    return {"id": s.id, "name": s.name, "start_time": s.start_time.strftime("%H:%M"),
            "end_time": s.end_time.strftime("%H:%M"), "overnight": s.end_time <= s.start_time,
            "break_minutes": s.break_minutes, "grace_minutes": s.grace_minutes, "color": s.color}


@shifts_router.get("")
def list_shifts(ctx: AuthContext = Depends(require("org.read")), db: Session = Depends(get_db)):
    return [_shift(s) for s in db.scalars(select(Shift).order_by(Shift.start_time))]


@shifts_router.post("", status_code=201)
def create_shift(body: ShiftIn, ctx: AuthContext = Depends(require("attendance.manage")),
                 db: Session = Depends(get_db)):
    if body.start_time == body.end_time:
        raise ValidationFailed("Start and end time cannot be equal")
    if db.scalar(select(Shift.id).where(Shift.name == body.name)):
        raise Conflict("A shift with this name exists", code="duplicate_name")
    s = Shift(tenant_id=ctx.tenant.id, **body.model_dump())
    db.add(s)
    db.commit()
    return _shift(s)


@shifts_router.put("/{shift_id}")
def update_shift(shift_id: uuid.UUID, body: ShiftIn, ctx: AuthContext = Depends(require("attendance.manage")),
                 db: Session = Depends(get_db)):
    s = db.get(Shift, shift_id)
    if s is None:
        raise NotFound("Shift not found")
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    db.commit()
    return _shift(s)


@shifts_router.delete("/{shift_id}", status_code=204)
def delete_shift(shift_id: uuid.UUID, ctx: AuthContext = Depends(require("attendance.manage")),
                 db: Session = Depends(get_db)):
    s = db.get(Shift, shift_id)
    if s is None:
        raise NotFound("Shift not found")
    if db.scalar(select(ShiftAssignment.id).where(ShiftAssignment.shift_id == s.id)):
        raise Conflict("This shift has assignments. Reassign employees first.", code="in_use")
    db.delete(s)
    db.commit()


@shifts_router.post("/assign")
def assign(body: AssignIn, ctx: AuthContext = Depends(require("attendance.manage")), db: Session = Depends(get_db)):
    """Assign a shift to employees (or a whole department) from a date. Closes the previous open assignment."""
    shift = db.get(Shift, body.shift_id)
    if shift is None:
        raise NotFound("Shift not found")
    ids = set(body.employee_ids)
    if body.department_id:
        ids |= set(db.scalars(select(Employee.id).where(
            Employee.department_id == body.department_id, Employee.deleted_at.is_(None),
            Employee.status.in_(LIVE_STATUSES))))
    if not ids:
        raise ValidationFailed("Select at least one employee or a department", code="no_targets")
    warnings, assigned = [], 0
    for emp in db.scalars(select(Employee).where(Employee.id.in_(ids), Employee.deleted_at.is_(None))):
        leave = db.scalar(select(LeaveRequest.id).where(
            LeaveRequest.employee_id == emp.id, LeaveRequest.status.in_(("approved", "pending")),
            LeaveRequest.end_date >= body.effective_from))
        if leave:
            warnings.append(f"{emp.full_name} has leave on or after {body.effective_from.isoformat()}")
        for a in db.scalars(select(ShiftAssignment).where(ShiftAssignment.employee_id == emp.id,
                                                          ShiftAssignment.effective_to.is_(None))):
            if a.effective_from < body.effective_from:
                a.effective_to = body.effective_from - timedelta(days=1)
            else:
                db.delete(a)
        db.flush()
        db.add(ShiftAssignment(tenant_id=ctx.tenant.id, employee_id=emp.id, shift_id=shift.id,
                               effective_from=body.effective_from))
        notify_employee(db, emp, "shift", f"Shift assigned: {shift.name}",
                        f"Effective from {body.effective_from}", "/me/attendance")
        assigned += 1
    tenancy.record_audit(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id, action="shift.assigned",
                         entity_type="shift", entity_id=shift.id,
                         details={"employees": assigned, "from": body.effective_from.isoformat()}, ip=ctx.ip)
    db.commit()
    return {"assigned": assigned, "warnings": warnings}


@shifts_router.get("/roster")
def roster(ctx: AuthContext = Depends(require("org.read")), db: Session = Depends(get_db)):
    """Current open assignment per employee."""
    shifts = {s.id: s for s in db.scalars(select(Shift))}
    emps = {e.id: e for e in db.scalars(select(Employee).where(Employee.deleted_at.is_(None),
                                                              Employee.status.in_(LIVE_STATUSES)))}
    names = emp_service.name_maps(db)
    current = {a.employee_id: a for a in db.scalars(
        select(ShiftAssignment).where(ShiftAssignment.effective_to.is_(None)))}
    return [{"employee_id": e.id, "employee_code": e.employee_code, "full_name": e.full_name,
             "department": names["department"].get(e.department_id),
             "shift_id": current[e.id].shift_id if e.id in current else None,
             "shift": (shifts[current[e.id].shift_id].name
                       if e.id in current and current[e.id].shift_id in shifts else None),
             "effective_from": current[e.id].effective_from if e.id in current else None}
            for e in sorted(emps.values(), key=lambda x: x.first_name)]

