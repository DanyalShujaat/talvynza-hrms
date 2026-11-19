from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.attendance.models import AttendanceAdjustment, AttendanceDaily
from app.modules.employees import service as emp_service
from app.modules.employees.models import LIVE_STATUSES, Employee
from app.modules.expenses.models import ExpenseClaim
from app.modules.helpdesk.models import Ticket
from app.modules.identity.deps import AuthContext, check_origin, get_tenant_ctx
from app.modules.leave import service as leave_service
from app.modules.leave.models import LeaveRequest
from app.modules.loans.models import Loan
from app.modules.notifications.models import Task
from app.modules.organization.models import Branch, Department, Designation, Holiday

router = APIRouter(tags=["reporting"], dependencies=[Depends(check_origin)])


def _count(db: Session, model, *where) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*where)) or 0


@router.get("/dashboard/stats")
def stats(ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    perms = ctx.permissions
    me = emp_service.current_employee(db, ctx.membership.id)
    today = date.today()
    out: dict = {"organization": None, "me": None, "alerts": [],
                 "approvals": {"leave": 0, "attendance": 0, "expenses": 0, "loans": 0, "tickets": 0}}

    # Approvals waiting on this user (their team, or everyone for HR)
    if me is not None or "leave.manage" in perms:
        team = emp_service.team_ids(db, me.id) - {me.id} if me else set()
        if "leave.approve" in perms:
            q = select(func.count()).select_from(LeaveRequest).where(LeaveRequest.status == "pending")
            if "leave.manage" not in perms:
                q = q.where(LeaveRequest.employee_id.in_(team))
            out["approvals"]["leave"] = db.scalar(q) or 0
        if "attendance.approve" in perms:
            q = select(func.count()).select_from(AttendanceAdjustment).where(AttendanceAdjustment.status == "pending")
            if "attendance.manage" not in perms:
                q = q.where(AttendanceAdjustment.employee_id.in_(team))
            out["approvals"]["attendance"] = db.scalar(q) or 0

    team_all = (emp_service.team_ids(db, me.id) - {me.id}) if me else set()
    if "expenses.finance_approve" in perms:
        no_manager = select(Employee.id).where(Employee.manager_id.is_(None))
        out["approvals"]["expenses"] = _count(
            db, ExpenseClaim, (ExpenseClaim.status == "manager_approved")
            | ((ExpenseClaim.status == "submitted") & ExpenseClaim.employee_id.in_(no_manager)))
    elif "expenses.approve" in perms:
        out["approvals"]["expenses"] = _count(db, ExpenseClaim, ExpenseClaim.status == "submitted",
                                              ExpenseClaim.employee_id.in_(team_all))
    if "loans.manage" in perms:
        out["approvals"]["loans"] = _count(db, Loan, Loan.status == "requested")
    if "helpdesk.manage" in perms:
        out["approvals"]["tickets"] = _count(db, Ticket, Ticket.status.in_(("open", "in_progress")))

    if me is not None:
        wd = today
        row = db.scalar(select(AttendanceDaily).where(AttendanceDaily.employee_id == me.id,
                                                      AttendanceDaily.work_date == wd))
        out["me"] = {
            "employee_name": me.full_name,
            "today_status": row.status if row else "not_checked_in",
            "first_in": row.first_in.isoformat() if row and row.first_in else None,
            "balances": [b for b in leave_service.balances(db, me.id) if b["entitled"] > 0],
            "open_tasks": _count(db, Task, Task.assignee_id == me.id, Task.status != "done"),
        }

    if "employees.read" not in perms:
        return out

    live = Employee.status.in_(LIVE_STATUSES)
    total = _count(db, Employee, Employee.deleted_at.is_(None), live)
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    global_holidays = {h.holiday_date for h in db.scalars(select(Holiday).where(
        Holiday.holiday_date >= days[0], Holiday.holiday_date <= today, Holiday.branch_id.is_(None)))}
    off = set(leave_service.weekend_days(db))
    chart = []
    for d in days:
        working = d.weekday() not in off and d not in global_holidays
        joined = _count(db, Employee, Employee.deleted_at.is_(None), Employee.joining_date <= d,
                        (Employee.exit_date.is_(None)) | (Employee.exit_date >= d))
        present = _count(db, AttendanceDaily, AttendanceDaily.work_date == d,
                         AttendanceDaily.status.in_(("present", "incomplete")))
        late = _count(db, AttendanceDaily, AttendanceDaily.work_date == d, AttendanceDaily.late_minutes > 0)
        on_leave = _count(db, LeaveRequest, LeaveRequest.status == "approved", LeaveRequest.start_date <= d,
                          LeaveRequest.end_date >= d)
        chart.append({"date": d.isoformat(), "working_day": working, "present": present, "late": late,
                      "absent": max(0, joined - present - on_leave) if working and d <= today else 0})
    t = chart[-1]
    out["organization"] = {
        "employees": total, "employee_limit": ctx.tenant.employee_capacity,
        "departments": _count(db, Department), "designations": _count(db, Designation),
        "branches": _count(db, Branch),
        "today": {"present": t["present"], "late": t["late"], "absent": t["absent"], "working_day": t["working_day"]},
        "late_last_7_days": sum(c["late"] for c in chart),
        "attendance_chart": chart,
    }
    soon = today + timedelta(days=30)
    for e in db.scalars(select(Employee).where(Employee.deleted_at.is_(None), Employee.contract_end.is_not(None),
                                               Employee.contract_end >= today, Employee.contract_end <= soon)):
        out["alerts"].append({"type": "contract_expiry", "employee": e.full_name, "date": e.contract_end.isoformat(),
                              "employee_id": str(e.id)})
    for e in db.scalars(select(Employee).where(Employee.deleted_at.is_(None), Employee.status == "probation",
                                               Employee.probation_end.is_not(None), Employee.probation_end <= soon)):
        out["alerts"].append({"type": "probation_ending", "employee": e.full_name,
                              "date": e.probation_end.isoformat(), "employee_id": str(e.id)})
    out["alerts"].sort(key=lambda a: a["date"])
    return out
