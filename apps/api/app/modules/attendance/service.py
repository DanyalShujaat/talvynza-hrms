"""Attendance persistence: punches, recalculation of daily summaries, corrections."""
from __future__ import annotations

import csv
import io
import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.db.base import utcnow
from app.modules.attendance import engine
from app.modules.attendance.models import (
    AttendanceAdjustment,
    AttendanceDaily,
    AttendanceEvent,
    AttendancePolicy,
    Shift,
    ShiftAssignment,
)
from app.modules.employees import service as emp_service
from app.modules.employees.models import Employee
from app.modules.leave.models import LeaveRequest
from app.modules.notifications import service as notifications
from app.modules.organization.models import Holiday
from app.modules.tenancy import service as tenancy
from app.modules.tenancy.models import Tenant

UTC = timezone.utc


def tz_of(tenant: Tenant) -> ZoneInfo:
    return ZoneInfo(tenant.timezone)


def get_policy(db: Session, tenant_id: uuid.UUID) -> AttendancePolicy:
    pol = db.scalar(select(AttendancePolicy))
    if pol is None:
        pol = AttendancePolicy(tenant_id=tenant_id)
        db.add(pol)
        db.flush()
    return pol


def current_shift_assignment(db: Session, employee_id: uuid.UUID, on: date) -> ShiftAssignment | None:
    return db.scalar(select(ShiftAssignment).where(
        ShiftAssignment.employee_id == employee_id, ShiftAssignment.effective_from <= on).where(
        (ShiftAssignment.effective_to.is_(None)) | (ShiftAssignment.effective_to >= on)
    ).order_by(ShiftAssignment.effective_from.desc()).limit(1))


def shift_for(db: Session, policy: AttendancePolicy, employee_id: uuid.UUID,
              on: date) -> tuple[engine.ShiftSpec, uuid.UUID | None]:
    a = current_shift_assignment(db, employee_id, on)
    if a is not None:
        s = db.get(Shift, a.shift_id)
        if s is not None:
            return engine.ShiftSpec(s.start_time, s.end_time, s.break_minutes, s.grace_minutes), s.id
    return engine.ShiftSpec(policy.default_start, policy.default_end, policy.default_break_minutes), None


def policy_spec(p: AttendancePolicy) -> engine.PolicySpec:
    return engine.PolicySpec(p.grace_minutes, p.late_mode, p.overtime_threshold_minutes)


def non_working_reason(db: Session, policy: AttendancePolicy, emp: Employee, on: date) -> str | None:
    holiday = db.scalar(select(Holiday).where(Holiday.holiday_date == on).where(
        (Holiday.branch_id.is_(None)) | (Holiday.branch_id == emp.branch_id)))
    if holiday is not None:
        return "holiday"
    if on.weekday() in (policy.weekend_days or []):
        return "weekend"
    return None


def on_leave(db: Session, employee_id: uuid.UUID, on: date) -> bool:
    return db.scalar(select(LeaveRequest.id).where(
        LeaveRequest.employee_id == employee_id, LeaveRequest.status == "approved",
        LeaveRequest.start_date <= on, LeaveRequest.end_date >= on)) is not None


def recompute(db: Session, tenant: Tenant, emp: Employee, work_date: date) -> AttendanceDaily:
    tz = tz_of(tenant)
    policy = get_policy(db, tenant.id)
    spec, shift_id = shift_for(db, policy, emp.id, work_date)
    lo, hi = work_date_window(db, policy, emp.id, work_date, tz)
    raw = db.scalars(select(AttendanceEvent).where(
        AttendanceEvent.employee_id == emp.id, AttendanceEvent.occurred_at >= lo, AttendanceEvent.occurred_at < hi))
    events = [(e.occurred_at, e.kind) for e in raw]
    reason = non_working_reason(db, policy, emp, work_date)
    res = engine.compute_day(work_date, spec, policy_spec(policy), tz, events, non_working=reason is not None)
    if res.status == "absent":
        if reason:
            res.status = reason
        elif on_leave(db, emp.id, work_date):
            res.status = "leave"
    row = db.scalar(select(AttendanceDaily).where(AttendanceDaily.employee_id == emp.id,
                                                  AttendanceDaily.work_date == work_date))
    if row is None:
        row = AttendanceDaily(tenant_id=tenant.id, employee_id=emp.id, work_date=work_date)
        db.add(row)
    row.shift_id, row.first_in, row.last_out = shift_id, res.first_in, res.last_out
    row.worked_minutes, row.late_minutes = res.worked_minutes, res.late_minutes
    row.early_leave_minutes, row.overtime_minutes, row.status = res.early_leave_minutes, res.overtime_minutes, res.status
    return row


def work_date_start(db: Session, policy: AttendancePolicy, employee_id: uuid.UUID, day: date, tz: ZoneInfo) -> datetime:
    """Keep every punch and give the prior overnight shift its after-midnight window."""
    midnight = datetime.combine(day, time.min, tzinfo=tz).astimezone(UTC)
    previous = day - timedelta(days=1)
    shift, _ = shift_for(db, policy, employee_id, previous)
    if not shift.overnight:
        return midnight
    _, overnight_end = engine.collection_window(previous, shift, tz)
    next_midnight = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC)
    return max(midnight, min(overnight_end, next_midnight))


def work_date_window(db: Session, policy: AttendancePolicy, employee_id: uuid.UUID,
                     day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    return (work_date_start(db, policy, employee_id, day, tz),
            work_date_start(db, policy, employee_id, day + timedelta(days=1), tz))


def work_date_for(db: Session, tenant: Tenant, emp: Employee, at: datetime) -> date:
    tz = tz_of(tenant)
    policy = get_policy(db, tenant.id)
    local = at.astimezone(tz).date()
    return local - timedelta(days=1) if at < work_date_start(db, policy, emp.id, local, tz) else local


def punch(db: Session, tenant: Tenant, emp: Employee, kind: str, at: datetime, *, source: str,
          actor: uuid.UUID | None) -> AttendanceDaily:
    if kind not in ("in", "out"):
        raise ValidationFailed("kind must be 'in' or 'out'")
    wd = work_date_for(db, tenant, emp, at)
    existing = db.scalar(select(AttendanceEvent).where(
        AttendanceEvent.employee_id == emp.id, AttendanceEvent.occurred_at == at, AttendanceEvent.kind == kind))
    if existing is None:
        db.add(AttendanceEvent(tenant_id=tenant.id, employee_id=emp.id, kind=kind, occurred_at=at, source=source,
                               created_by=actor))
        db.flush()
    row = recompute(db, tenant, emp, wd)
    db.commit()
    return row


def open_state(db: Session, tenant: Tenant, emp: Employee, at: datetime) -> str:
    """'in' if the employee is currently clocked in, otherwise 'out'."""
    wd = work_date_for(db, tenant, emp, at)
    policy = get_policy(db, tenant.id)
    lo, hi = work_date_window(db, policy, emp.id, wd, tz_of(tenant))
    evs = db.scalars(select(AttendanceEvent).where(
        AttendanceEvent.employee_id == emp.id, AttendanceEvent.occurred_at >= lo, AttendanceEvent.occurred_at < hi))
    _, dangling = engine.pair_punches([(e.occurred_at, e.kind) for e in evs])
    return "in" if dangling else "out"


def check(db: Session, tenant: Tenant, emp: Employee, kind: str, actor: uuid.UUID, *, source: str = "web") -> AttendanceDaily:
    now = utcnow().replace(microsecond=0)
    state = open_state(db, tenant, emp, now)
    if kind == "in" and state == "in":
        raise Conflict("You are already checked in", code="already_checked_in")
    if kind == "out" and state == "out":
        raise Conflict("You are not checked in", code="not_checked_in")
    return punch(db, tenant, emp, kind, now, source=source, actor=actor)


# ------------------------------------------------------------------ import
def import_punches(db: Session, tenant: Tenant, actor: uuid.UUID, data: bytes, *, branch_id: uuid.UUID | None = None) -> dict:
    """CSV columns: employee_code (or bio_id), timestamp (ISO 8601, UTC if no offset), optional kind (in/out).
    Missing kinds alternate in/out per employee per day. Duplicate reads are ignored."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValidationFailed("CSV must be UTF-8 encoded", code="bad_file") from None
    reader = csv.DictReader(io.StringIO(text))
    fields = {f.strip().lower() for f in reader.fieldnames or []}
    if "timestamp" not in fields:
        raise ValidationFailed("CSV needs a 'timestamp' column", code="bad_file")
    if branch_id is not None and "bio_id" not in fields:
        raise ValidationFailed("A biometric export needs a 'bio_id' column", code="bad_file")
    if branch_id is None and "employee_code" not in fields:
        raise ValidationFailed("Select the device branch to import biometric IDs", code="branch_required")
    emps = list(db.scalars(select(Employee).where(Employee.deleted_at.is_(None))))
    by_code = {e.employee_code: e for e in emps}
    by_bio: dict[str, list[Employee]] = {}
    for emp in emps:
        if branch_id is not None and emp.branch_id == branch_id and emp.bio_id:
            by_bio.setdefault(emp.bio_id, []).append(emp)
    imported, skipped, errors = 0, 0, []
    seen: set[tuple[uuid.UUID, datetime, str]] = set()  # rows added in this file are not flushed yet
    touched: set[tuple[uuid.UUID, date]] = set()
    counters: dict[tuple[uuid.UUID, date], int] = {}
    rows = []
    implicit_seen: set[tuple[uuid.UUID, datetime]] = set()
    for i, raw in enumerate(reader, start=2):
        row = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
        if branch_id is None:
            emp = by_code.get(row.get("employee_code", ""))
        else:
            matches = by_bio.get(row.get("bio_id", ""), [])
            if len(matches) > 1:
                errors.append({"row": i, "error": "biometric ID is shared by multiple employees in this branch"})
                continue
            emp = matches[0] if matches else None
        if emp is None:
            errors.append({"row": i, "error": "unknown biometric ID for this branch" if branch_id else "unknown employee"})
            continue
        if branch_id is not None and not emp.premises_attendance_enabled:
            errors.append({"row": i, "error": "premises attendance is disabled for this employee"})
            continue
        try:
            at = datetime.fromisoformat(row["timestamp"])
        except (KeyError, ValueError):
            errors.append({"row": i, "error": "invalid timestamp"})
            continue
        if at.tzinfo is None:
            at = at.replace(tzinfo=tz_of(tenant) if branch_id else UTC)
        at = at.astimezone(UTC).replace(microsecond=0)
        kind = row.get("kind", "").lower()
        if kind and kind not in ("in", "out"):
            errors.append({"row": i, "error": "kind must be 'in' or 'out'"})
            continue
        rows.append((at, i, emp, kind))
    for at, _, emp, kind in sorted(rows, key=lambda row: (row[0], row[1])):
        wd = work_date_for(db, tenant, emp, at)
        key = (emp.id, wd)
        if not kind:
            if (emp.id, at) in implicit_seen:
                skipped += 1
                continue
            implicit_seen.add((emp.id, at))
            kind = "in" if counters.get(key, 0) % 2 == 0 else "out"
        counters[key] = 1 if kind == "in" else 0
        if (emp.id, at, kind) in seen or db.scalar(select(AttendanceEvent.id).where(
                AttendanceEvent.employee_id == emp.id, AttendanceEvent.occurred_at == at,
                AttendanceEvent.kind == kind)):
            skipped += 1
            continue
        seen.add((emp.id, at, kind))
        db.add(AttendanceEvent(tenant_id=tenant.id, employee_id=emp.id, kind=kind, occurred_at=at,
                               source="biometric" if branch_id else "import",
                               created_by=actor))
        touched.add(key)
        imported += 1
    db.flush()
    by_id = {e.id: e for e in emps}
    for emp_id, wd in touched:
        recompute(db, tenant, by_id[emp_id], wd)
    tenancy.record_audit(db, tenant_id=tenant.id, actor=actor, action="attendance.imported", entity_type="attendance",
                         details={"imported": imported, "duplicates": skipped, "errors": len(errors),
                                  "branch_id": str(branch_id) if branch_id else None})
    db.commit()
    return {"imported": imported, "duplicates_ignored": skipped, "error_count": len(errors), "errors": errors[:50]}


# ------------------------------------------------------------------ corrections
def _to_utc(tz: ZoneInfo, d: date, hhmm: str) -> datetime:
    try:
        h, m = (int(x) for x in hhmm.split(":"))
        return datetime.combine(d, time(h, m), tzinfo=tz).astimezone(UTC)
    except ValueError:
        raise ValidationFailed("Time must be HH:MM", details=[{"field": "time"}]) from None


def request_adjustment(db: Session, tenant: Tenant, emp: Employee, actor: uuid.UUID, work_date: date,
                       in_time: str | None, out_time: str | None, reason: str) -> AttendanceAdjustment:
    if not in_time and not out_time:
        raise ValidationFailed("Provide an in time, an out time or both", code="missing_times")
    if work_date > date.today():
        raise ValidationFailed("You cannot correct a future date", code="future_date")
    tz = tz_of(tenant)
    r_in = _to_utc(tz, work_date, in_time) if in_time else None
    r_out = _to_utc(tz, work_date, out_time) if out_time else None
    if r_out and r_in and r_out <= r_in:
        r_out += timedelta(days=1)  # overnight
    if db.scalar(select(AttendanceAdjustment.id).where(
            AttendanceAdjustment.employee_id == emp.id, AttendanceAdjustment.work_date == work_date,
            AttendanceAdjustment.status == "pending")):
        raise Conflict("A correction for this date is already pending", code="duplicate_pending")
    adj = AttendanceAdjustment(tenant_id=tenant.id, employee_id=emp.id, work_date=work_date, requested_in=r_in,
                               requested_out=r_out, reason=reason.strip(), status="pending")
    db.add(adj)
    tenancy.record_audit(db, tenant_id=tenant.id, actor=actor, action="attendance.correction_requested",
                         entity_type="attendance_adjustment", details={"date": work_date.isoformat()})
    db.flush()
    title = f"Time adjustment from {emp.full_name}"
    key = f"attendance-adjustment:{adj.id}"
    if emp.manager_id:
        notifications.notify_employee(db, db.get(Employee, emp.manager_id), "attendance", title,
                                      f"Date: {work_date}", f"/inbox/attendance/{adj.id}", dedupe_key=key)
    notifications.notify_permission_holders(db, tenant.id, "attendance.manage", "attendance", title,
                                            f"Date: {work_date}", f"/inbox/attendance/{adj.id}", dedupe_key=key,
                                            exclude_identity_id=actor)
    db.commit()
    return adj


def decide_adjustment(db: Session, tenant: Tenant, actor: uuid.UUID, perms: set[str], me: Employee | None,
                      adj: AttendanceAdjustment, approve: bool, note: str | None) -> AttendanceAdjustment:
    if me is not None and me.id == adj.employee_id:
        raise Forbidden("You cannot approve your own correction", code="self_approval")
    if "attendance.manage" not in perms:
        if me is None or adj.employee_id not in emp_service.team_ids(db, me.id):
            raise NotFound("Request not found")
    if adj.status != "pending":
        raise Conflict("This request has already been decided", code="already_decided")
    adj.status = "approved" if approve else "rejected"
    adj.reviewed_by, adj.reviewed_at, adj.review_note = actor, utcnow(), note
    if approve:
        emp = emp_service.get_employee(db, adj.employee_id)
        for kind, at in (("in", adj.requested_in), ("out", adj.requested_out)):
            if at is None:
                continue
            if not db.scalar(select(AttendanceEvent.id).where(
                    AttendanceEvent.employee_id == emp.id, AttendanceEvent.occurred_at == at,
                    AttendanceEvent.kind == kind)):
                db.add(AttendanceEvent(tenant_id=tenant.id, employee_id=emp.id, kind=kind, occurred_at=at,
                                       source="adjustment", created_by=actor))
        db.flush()
        recompute(db, tenant, emp, adj.work_date)
    tenancy.record_audit(db, tenant_id=tenant.id, actor=actor, action=f"attendance.correction_{adj.status}",
                         entity_type="attendance_adjustment", entity_id=adj.id)
    notifications.notify_employee(db, emp_service.get_employee(db, adj.employee_id), "attendance",
                                  f"Your time adjustment was {adj.status}", note, "/me/attendance?tab=adjust")
    db.commit()
    return adj
