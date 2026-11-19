"""Tabular reports. Every figure is computed from stored records at request time."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.attendance.models import AttendanceDaily
from app.modules.common import me_of
from app.modules.employees import service as emp_service
from app.modules.employees.models import LIVE_STATUSES, Employee
from app.modules.identity.deps import AuthContext, check_origin, require
from app.modules.leave import service as leave_service
from app.modules.leave.models import LeaveType
from app.modules.payroll.models import PayrollEntry, PayrollRun

router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(check_origin)])
view = require("reports.view")


def _visible(db: Session, ctx: AuthContext) -> list[Employee]:
    allowed = emp_service.visible_ids(db, ctx.permissions, me_of(db, ctx))
    stmt = select(Employee).where(Employee.deleted_at.is_(None)).order_by(Employee.first_name, Employee.last_name)
    if allowed is not None:
        stmt = stmt.where(Employee.id.in_(allowed))
    return list(db.scalars(stmt))


def _group(emps: list[Employee], key, names: dict) -> list[dict]:
    out: dict = {}
    for e in emps:
        label = names.get(key(e)) or "Unassigned"
        out[label] = out.get(label, 0) + 1
    return [{"label": k, "count": v} for k, v in sorted(out.items(), key=lambda x: -x[1])]


@router.get("/headcount")
def headcount(ctx: AuthContext = Depends(view), db: Session = Depends(get_db)):
    emps = _visible(db, ctx)
    live = [e for e in emps if e.status in LIVE_STATUSES]
    names = emp_service.name_maps(db)
    today = date.today()
    months = []
    y, m = today.year, today.month
    for _ in range(12):
        first = date(y, m, 1)
        nxt = date(y + (m == 12), m % 12 + 1, 1)
        months.append({"month": first.strftime("%Y-%m"),
                       "joined": sum(1 for e in emps if first <= e.joining_date < nxt),
                       "left": sum(1 for e in emps if e.exit_date and first <= e.exit_date < nxt)})
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    status: dict = {}
    for e in emps:
        status[e.status] = status.get(e.status, 0) + 1
    etype: dict = {}
    for e in live:
        etype[e.employment_type] = etype.get(e.employment_type, 0) + 1
    return {"total": len(live),
            "by_department": _group(live, lambda e: e.department_id, names["department"]),
            "by_branch": _group(live, lambda e: e.branch_id, names["branch"]),
            "by_status": [{"label": k, "count": v} for k, v in sorted(status.items())],
            "by_employment_type": [{"label": k, "count": v} for k, v in sorted(etype.items())],
            "movement": list(reversed(months))}


@router.get("/attendance")
def attendance(month: str = Query(pattern=r"^\d{4}-\d{2}$"), ctx: AuthContext = Depends(view),
               db: Session = Depends(get_db)):
    y, m = int(month[:4]), int(month[5:])
    first = date(y, m, 1)
    last = min(date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1), date.today())
    emps = [e for e in _visible(db, ctx) if e.status in LIVE_STATUSES]
    names = emp_service.name_maps(db)
    rows = db.scalars(select(AttendanceDaily).where(AttendanceDaily.work_date >= first, AttendanceDaily.work_date <= last,
                                                    AttendanceDaily.employee_id.in_([e.id for e in emps]))).all()
    by: dict = {}
    for r in rows:
        by.setdefault(r.employee_id, []).append(r)
    out = []
    for e in emps:
        days = by.get(e.id, [])
        start = max(first, e.joining_date)
        working = leave_service.count_working_days(db, start, last, e.branch_id) if start <= last else 0
        present = sum(1 for d in days if d.status in ("present", "incomplete"))
        leave = sum(1 for d in days if d.status == "leave")
        out.append({"employee_id": e.id, "employee_code": e.employee_code, "employee": e.full_name,
                    "department": names["department"].get(e.department_id), "working_days": working,
                    "present_days": present, "leave_days": leave, "absent_days": max(0, working - present - leave),
                    "late_days": sum(1 for d in days if d.late_minutes > 0),
                    "late_minutes": sum(d.late_minutes for d in days),
                    "worked_hours": round(sum(d.worked_minutes for d in days) / 60, 1),
                    "overtime_hours": round(sum(d.overtime_minutes for d in days) / 60, 1)})
    return {"month": month, "rows": out}


@router.get("/leave")
def leave(year: int = Query(ge=2000, le=2100), ctx: AuthContext = Depends(view), db: Session = Depends(get_db)):
    emps = [e for e in _visible(db, ctx) if e.status in LIVE_STATUSES]
    names = emp_service.name_maps(db)
    types = list(db.scalars(select(LeaveType).where(LeaveType.is_active.is_(True)).order_by(LeaveType.name)))
    out = []
    for e in emps:
        for lt in types:
            b = leave_service.balance(db, e.id, lt, year)
            if b["entitled"] or b["used"] or b["reserved"]:
                out.append({"employee_code": e.employee_code, "employee": e.full_name,
                            "department": names["department"].get(e.department_id), "leave_type": lt.name,
                            "entitled": b["entitled"], "used": b["used"], "pending": b["reserved"],
                            "available": b["available"]})
    return {"year": year, "rows": out}


@router.get("/payroll")
def payroll(year: int = Query(ge=2000, le=2100), ctx: AuthContext = Depends(require("reports.view", "payroll.read")),
            db: Session = Depends(get_db)):
    runs = db.scalars(select(PayrollRun).where(PayrollRun.status == "finalized",
                                               PayrollRun.period_end >= date(year, 1, 1),
                                               PayrollRun.period_end <= date(year, 12, 31))
                      .order_by(PayrollRun.period_start)).all()
    names = emp_service.name_maps(db)
    dept_of = {e.id: names["department"].get(e.department_id) or "Unassigned" for e in db.scalars(select(Employee))}
    monthly, by_dept = [], {}
    for r in runs:
        tax = db.scalar(select(func.coalesce(func.sum(PayrollEntry.income_tax), 0)).where(PayrollEntry.run_id == r.id))
        count = db.scalar(select(func.count()).select_from(PayrollEntry).where(PayrollEntry.run_id == r.id))
        monthly.append({"period": f"{r.period_start.isoformat()} to {r.period_end.isoformat()}",
                        "month": r.period_end.strftime("%Y-%m"), "employees": count, "gross": r.total_gross,
                        "deductions": r.total_deductions, "income_tax": Decimal(str(tax)), "net": r.total_net})
        for e in db.scalars(select(PayrollEntry).where(PayrollEntry.run_id == r.id)):
            d = by_dept.setdefault(dept_of.get(e.employee_id, "Unassigned"), [Decimal("0"), Decimal("0")])
            d[0] += e.gross
            d[1] += e.net
    return {"year": year, "currency": ctx.tenant.currency, "runs": monthly,
            "by_department": [{"department": k, "gross": v[0], "net": v[1]} for k, v in sorted(by_dept.items())]}
