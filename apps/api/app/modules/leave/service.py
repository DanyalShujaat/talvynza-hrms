"""Leave rules. Balances are always derived from the ledger, never stored as a mutable total."""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.db.base import utcnow
from app.modules.attendance.models import AttendancePolicy
from app.modules.employees import service as emp_service
from app.modules.employees.models import LIVE_STATUSES, Employee
from app.modules.leave.models import LeaveLedgerEntry, LeaveRequest, LeaveType
from app.modules.notifications import service as notifications
from app.modules.organization.models import Holiday
from app.modules.tenancy import service as tenancy

ZERO = Decimal("0")
HALF = Decimal("0.5")
DEFAULT_TYPES = [
    # name, days/yr, paid, allow_negative, after_probation, carry_forward_max
    ("Annual Leave", "20", True, False, True, "5"),
    ("Casual Leave", "10", True, False, False, "0"),
    ("Sick Leave", "8", True, False, False, "0"),
    ("Unpaid Leave", "0", False, True, False, "0"),
]


def weekend_days(db: Session) -> list[int]:
    pol = db.scalar(select(AttendancePolicy))
    return list(pol.weekend_days) if pol else [5, 6]


def holiday_dates(db: Session, start: date, end: date, branch_id: uuid.UUID | None) -> set[date]:
    rows = db.scalars(select(Holiday).where(Holiday.holiday_date >= start, Holiday.holiday_date <= end))
    return {h.holiday_date for h in rows if h.branch_id is None or h.branch_id == branch_id}


def count_working_days(db: Session, start: date, end: date, branch_id: uuid.UUID | None) -> int:
    off = set(weekend_days(db))
    holidays = holiday_dates(db, start, end, branch_id)
    n, d = 0, start
    while d <= end:
        if d.weekday() not in off and d not in holidays:
            n += 1
        d += timedelta(days=1)
    return n


def ensure_default_types(db: Session, tenant_id: uuid.UUID) -> None:
    if db.scalar(select(func.count()).select_from(LeaveType)):
        return
    for name, days, paid, neg, after, cf in DEFAULT_TYPES:
        db.add(LeaveType(tenant_id=tenant_id, name=name, days_per_year=Decimal(days), is_paid=paid,
                         allow_negative=neg, after_probation=after, carry_forward_max=Decimal(cf)))
    db.commit()


def _sum(db: Session, employee_id: uuid.UUID, type_id: uuid.UUID, kinds: tuple[str, ...], year: int) -> Decimal:
    v = db.scalar(select(func.coalesce(func.sum(LeaveLedgerEntry.days), 0)).where(
        LeaveLedgerEntry.employee_id == employee_id, LeaveLedgerEntry.leave_type_id == type_id,
        LeaveLedgerEntry.entry_type.in_(kinds), LeaveLedgerEntry.effective_date >= date(year, 1, 1),
        LeaveLedgerEntry.effective_date <= date(year, 12, 31)))
    return Decimal(str(v))


def balance(db: Session, employee_id: uuid.UUID, lt: LeaveType, year: int | None = None) -> dict:
    """Balance for one leave year. Requests count toward the year in which they start."""
    year = year or date.today().year
    entitled = _sum(db, employee_id, lt.id, ("grant", "carry_forward", "adjustment"), year)
    used = -_sum(db, employee_id, lt.id, ("used", "restored"), year)
    reserved = -_sum(db, employee_id, lt.id, ("reserved", "released"), year)
    return {"leave_type_id": lt.id, "name": lt.name, "is_paid": lt.is_paid, "year": year, "entitled": entitled,
            "used": used, "reserved": reserved, "available": entitled - used - reserved,
            "carried_forward": _sum(db, employee_id, lt.id, ("carry_forward",), year)}


def balances(db: Session, employee_id: uuid.UUID, year: int | None = None) -> list[dict]:
    return [balance(db, employee_id, lt, year) for lt in db.scalars(
        select(LeaveType).where(LeaveType.is_active.is_(True)).order_by(LeaveType.name))]


def _ledger(db: Session, tenant_id, emp_id, type_id, kind: str, days: Decimal, on: date, *, request_id=None,
            ref_key=None, note=None, actor=None) -> None:
    db.add(LeaveLedgerEntry(tenant_id=tenant_id, employee_id=emp_id, leave_type_id=type_id, entry_type=kind,
                            days=days, effective_date=on, request_id=request_id, ref_key=ref_key, note=note,
                            created_by=actor, created_at=utcnow()))


def apply(db: Session, *, tenant_id: uuid.UUID, actor: uuid.UUID, emp: Employee, type_id: uuid.UUID, start: date,
          end: date, half_day: bool, reason: str | None) -> LeaveRequest:
    lt = db.get(LeaveType, type_id)
    if lt is None or not lt.is_active:
        raise ValidationFailed("Unknown leave type", details=[{"field": "leave_type_id"}])
    if end < start:
        raise ValidationFailed("End date is before the start date", details=[{"field": "end_date"}])
    if emp.status not in LIVE_STATUSES or emp.status == "suspended":
        raise Conflict("This employee cannot request leave in their current status", code="invalid_status")
    if lt.after_probation and emp.status == "probation":
        raise Conflict(f"{lt.name} is not available during probation", code="probation_restricted")
    if half_day:
        if not lt.allow_half_day:
            raise ValidationFailed(f"{lt.name} does not allow half days", code="half_day_not_allowed")
        if start != end:
            raise ValidationFailed("A half day must be a single date", code="half_day_range")
    working = count_working_days(db, start, end, emp.branch_id)
    if working == 0:
        raise ValidationFailed("The selected dates are all weekends or holidays", code="no_working_days")
    days = HALF if half_day else Decimal(working)
    overlap = db.scalar(select(func.count()).select_from(LeaveRequest).where(
        LeaveRequest.employee_id == emp.id, LeaveRequest.status.in_(("pending", "approved")),
        LeaveRequest.start_date <= end, LeaveRequest.end_date >= start))
    if overlap:
        raise Conflict("You already have leave requested for these dates", code="overlapping_leave")
    bal = balance(db, emp.id, lt, start.year)
    if days > bal["available"] and not lt.allow_negative:
        raise Conflict(f"Insufficient {lt.name} balance: {bal['available']} available, {days} requested",
                       code="insufficient_balance")
    req = LeaveRequest(tenant_id=tenant_id, employee_id=emp.id, leave_type_id=lt.id, start_date=start, end_date=end,
                       half_day=half_day, days=days, reason=reason, status="pending")
    db.add(req)
    db.flush()
    _ledger(db, tenant_id, emp.id, lt.id, "reserved", -days, start, request_id=req.id, actor=actor)
    tenancy.record_audit(db, tenant_id=tenant_id, actor=actor, action="leave.requested", entity_type="leave_request",
                         entity_id=req.id, details={"days": str(days)})
    title = f"Leave request from {emp.full_name}"
    key = f"leave-request:{req.id}"
    if emp.manager_id:
        notifications.notify_employee(db, db.get(Employee, emp.manager_id), "leave", title,
                                      f"{lt.name}: {start} to {end}", f"/inbox/leave/{req.id}", dedupe_key=key)
    notifications.notify_permission_holders(db, tenant_id, "leave.manage", "leave", title,
                                            f"{lt.name}: {start} to {end}", f"/inbox/leave/{req.id}", dedupe_key=key,
                                            exclude_identity_id=actor)
    db.commit()
    return req


def _can_decide(db: Session, perms: set[str], me: Employee | None, req: LeaveRequest) -> None:
    if me is not None and me.id == req.employee_id:
        raise Forbidden("You cannot approve your own request", code="self_approval")
    if "leave.manage" in perms:
        return
    if "leave.approve" in perms and me is not None and req.employee_id in emp_service.team_ids(db, me.id):
        return
    raise NotFound("Leave request not found")


def decide(db: Session, *, tenant_id: uuid.UUID, actor: uuid.UUID, perms: set[str], me: Employee | None,
           req: LeaveRequest, approve: bool, note: str | None) -> LeaveRequest:
    _can_decide(db, perms, me, req)
    if req.status != "pending":
        raise Conflict("This request has already been decided", code="already_decided")
    _ledger(db, tenant_id, req.employee_id, req.leave_type_id, "released", req.days, req.start_date,
            request_id=req.id, actor=actor)
    if approve:
        _ledger(db, tenant_id, req.employee_id, req.leave_type_id, "used", -req.days, req.start_date,
                request_id=req.id, actor=actor)
    req.status = "approved" if approve else "rejected"
    req.decided_by, req.decided_at, req.decision_note = actor, utcnow(), note
    tenancy.record_audit(db, tenant_id=tenant_id, actor=actor, action=f"leave.{req.status}",
                         entity_type="leave_request", entity_id=req.id)
    notifications.notify_employee(db, emp_service.get_employee(db, req.employee_id), "leave",
                                  f"Your leave request was {req.status}", note, "/me/leave")
    db.commit()
    return req


def cancel(db: Session, *, tenant_id: uuid.UUID, actor: uuid.UUID, perms: set[str], me: Employee | None,
           req: LeaveRequest) -> LeaveRequest:
    own = me is not None and me.id == req.employee_id
    if not own and "leave.manage" not in perms:
        raise NotFound("Leave request not found")
    if req.status == "pending":
        _ledger(db, tenant_id, req.employee_id, req.leave_type_id, "released", req.days, req.start_date,
                request_id=req.id, actor=actor)
    elif req.status == "approved":
        if req.start_date <= date.today() and "leave.manage" not in perms:
            raise Conflict("Leave that has already started can only be cancelled by HR", code="already_started")
        _ledger(db, tenant_id, req.employee_id, req.leave_type_id, "restored", req.days, req.start_date,
                request_id=req.id, actor=actor)
    else:
        raise Conflict("This request can no longer be cancelled", code="not_cancellable")
    req.status = "cancelled"
    tenancy.record_audit(db, tenant_id=tenant_id, actor=actor, action="leave.cancelled", entity_type="leave_request",
                         entity_id=req.id)
    db.commit()
    return req


def _round_half(d: Decimal) -> Decimal:
    return (d * 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP) / 2


def entitlement_for(days_per_year: Decimal, joining: date, year: int) -> Decimal:
    """Pro-rated by whole months remaining when the employee joined during the leave year."""
    if joining.year > year:
        return ZERO
    if joining.year < year:
        return days_per_year
    months_left = 12 - joining.month + 1
    return _round_half(days_per_year * Decimal(months_left) / Decimal(12))


def grant_year(db: Session, *, tenant_id: uuid.UUID, actor: uuid.UUID, year: int) -> int:
    """Idempotent: a (employee, type, year) grant is written once, guarded by a unique ref_key."""
    created = 0
    types = [lt for lt in db.scalars(select(LeaveType).where(LeaveType.is_active.is_(True))) if lt.days_per_year > 0]
    for emp in db.scalars(select(Employee).where(Employee.deleted_at.is_(None), Employee.status.in_(LIVE_STATUSES))):
        for lt in types:
            key = f"grant:{year}"
            exists = db.scalar(select(func.count()).select_from(LeaveLedgerEntry).where(
                LeaveLedgerEntry.employee_id == emp.id, LeaveLedgerEntry.leave_type_id == lt.id,
                LeaveLedgerEntry.ref_key == key))
            days = entitlement_for(lt.days_per_year, emp.joining_date, year)
            if exists or days <= 0:
                continue
            _ledger(db, tenant_id, emp.id, lt.id, "grant", days, date(year, 1, 1), ref_key=key,
                    note=f"{year} entitlement", actor=actor)
            created += 1
    tenancy.record_audit(db, tenant_id=tenant_id, actor=actor, action="leave.grants_run", entity_type="leave",
                         details={"year": year, "entries": created})
    db.commit()
    return created


def carry_forward(db: Session, *, tenant_id: uuid.UUID, actor: uuid.UUID, from_year: int) -> int:
    """Carries unused balance (capped per type) into the next year. Idempotent per employee, type and year."""
    created = 0
    for lt in db.scalars(select(LeaveType).where(LeaveType.carry_forward_max > 0)):
        for emp in db.scalars(select(Employee).where(Employee.deleted_at.is_(None),
                                                     Employee.status.in_(LIVE_STATUSES))):
            key = f"carry:{from_year + 1}"
            if db.scalar(select(func.count()).select_from(LeaveLedgerEntry).where(
                    LeaveLedgerEntry.employee_id == emp.id, LeaveLedgerEntry.leave_type_id == lt.id,
                    LeaveLedgerEntry.ref_key == key)):
                continue
            avail = balance(db, emp.id, lt, from_year)["available"]
            carry = min(max(avail, ZERO), lt.carry_forward_max)
            if carry > 0:
                _ledger(db, tenant_id, emp.id, lt.id, "carry_forward", carry, date(from_year + 1, 1, 1),
                        ref_key=key, note=f"Carried from {from_year}", actor=actor)
                created += 1
    db.commit()
    return created


def _on_tenant_created(payload: dict) -> None:
    db: Session = payload["db"]
    from app.db.tenant_scope import tenant_scope

    with tenant_scope(db, payload["tenant_id"]):
        ensure_default_types(db, payload["tenant_id"])
        from app.modules.attendance.service import get_policy

        get_policy(db, payload["tenant_id"])
    db.commit()


def register_handlers() -> None:
    from app.core import events

    events.subscribe("tenant.created", _on_tenant_created)
