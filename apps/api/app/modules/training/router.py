from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.db.session import get_db
from app.modules.common import audit, emp_map, me_of, need_any, need_me
from app.modules.employees.models import LIVE_STATUSES, Employee
from app.modules.identity.deps import AuthContext, check_origin, get_tenant_ctx, require
from app.modules.notifications.service import notify_employee
from app.modules.training.models import Course, Enrollment

router = APIRouter(tags=["training"], dependencies=[Depends(check_origin)])
manage = require("training.manage")


class CourseIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    category: str = Field(default="General", max_length=60)
    mandatory: bool = False
    url: str | None = Field(default=None, max_length=500, pattern=r"^https?://")
    duration_hours: Decimal | None = Field(default=None, gt=0, le=1000)
    is_active: bool = True


class AssignIn(BaseModel):
    employee_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    department_id: uuid.UUID | None = None
    everyone: bool = False
    due_date: date | None = None


class EnrollmentPatch(BaseModel):
    status: str = Field(pattern="^(assigned|in_progress|completed)$")


def _course(c: Course, stats: dict) -> dict:
    total, done = stats.get(c.id, (0, 0))
    return {"id": c.id, "title": c.title, "description": c.description, "category": c.category,
            "mandatory": c.mandatory, "url": c.url, "duration_hours": c.duration_hours, "is_active": c.is_active,
            "enrolled": total, "completed": done}


def _stats(db: Session) -> dict:
    out: dict = {}
    for cid, status, n in db.execute(select(Enrollment.course_id, Enrollment.status, func.count())
                                     .group_by(Enrollment.course_id, Enrollment.status)).all():
        total, done = out.get(cid, (0, 0))
        out[cid] = (total + n, done + (n if status == "completed" else 0))
    return out


@router.get("/courses")
def list_courses(ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    stmt = select(Course).order_by(Course.title)
    if "training.manage" not in ctx.permissions:
        stmt = stmt.where(Course.is_active.is_(True))
    stats = _stats(db)
    return [_course(c, stats) for c in db.scalars(stmt)]


@router.post("/courses", status_code=201)
def create_course(body: CourseIn, ctx: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    if db.scalar(select(Course.id).where(func.lower(Course.title) == body.title.lower())):
        raise Conflict("A course with this title exists", code="duplicate_name")
    c = Course(tenant_id=ctx.tenant.id, **body.model_dump())
    db.add(c)
    db.commit()
    return _course(c, {})


@router.put("/courses/{course_id}")
def update_course(course_id: uuid.UUID, body: CourseIn, ctx: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    c = db.get(Course, course_id)
    if c is None:
        raise NotFound("Course not found")
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    db.commit()
    return _course(c, _stats(db))


def _enroll(db: Session, ctx: AuthContext, course: Course, emp: Employee, due: date | None, notify: bool) -> bool:
    if db.scalar(select(Enrollment.id).where(Enrollment.course_id == course.id, Enrollment.employee_id == emp.id)):
        return False
    db.add(Enrollment(tenant_id=ctx.tenant.id, course_id=course.id, employee_id=emp.id, due_date=due,
                      assigned_by=ctx.identity.id))
    if notify:
        notify_employee(db, emp, "training", f"Training assigned: {course.title}",
                        f"Due {due.isoformat()}" if due else None, "/me/training")
    return True


@router.post("/courses/{course_id}/assign")
def assign(course_id: uuid.UUID, body: AssignIn, ctx: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    course = db.get(Course, course_id)
    if course is None or not course.is_active:
        raise NotFound("Course not found")
    stmt = select(Employee).where(Employee.deleted_at.is_(None), Employee.status.in_(LIVE_STATUSES))
    if body.everyone:
        pass
    elif body.department_id:
        stmt = stmt.where(Employee.department_id == body.department_id)
    elif body.employee_ids:
        stmt = stmt.where(Employee.id.in_(body.employee_ids))
    else:
        raise ValidationFailed("Choose employees, a department or everyone", code="no_targets")
    added = sum(_enroll(db, ctx, course, e, body.due_date, True) for e in db.scalars(stmt))
    audit(db, ctx, "training.assigned", "course", course.id, {"employees": added})
    db.commit()
    return {"assigned": added}


@router.post("/courses/{course_id}/enroll", status_code=201)
def self_enroll(course_id: uuid.UUID, ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    me = need_me(db, ctx)
    course = db.get(Course, course_id)
    if course is None or not course.is_active:
        raise NotFound("Course not found")
    if not _enroll(db, ctx, course, me, None, False):
        raise Conflict("You are already enrolled in this course", code="already_enrolled")
    db.commit()
    return {"ok": True}


def _enrollment(e: Enrollment, courses: dict, emps: dict) -> dict:
    c, emp = courses.get(e.course_id), emps.get(e.employee_id)
    return {"id": e.id, "course_id": e.course_id, "course": c.title if c else None, "category": c.category if c else None,
            "mandatory": bool(c and c.mandatory), "url": c.url if c else None,
            "duration_hours": c.duration_hours if c else None, "employee_id": e.employee_id,
            "employee": emp.full_name if emp else None, "status": e.status, "due_date": e.due_date,
            "completed_on": e.completed_on,
            "overdue": bool(e.due_date and e.due_date < date.today() and e.status != "completed")}


@router.get("/enrollments")
def list_enrollments(scope: str = Query("mine", pattern="^(mine|all)$"), course_id: uuid.UUID | None = None,
                     ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    me = me_of(db, ctx)
    stmt = select(Enrollment).order_by(Enrollment.created_at.desc()).limit(1000)
    if scope == "all":
        need_any(ctx, "training.manage")
    else:
        if me is None:
            return []
        stmt = stmt.where(Enrollment.employee_id == me.id)
    if course_id:
        stmt = stmt.where(Enrollment.course_id == course_id)
    rows = db.scalars(stmt).all()
    courses = {c.id: c for c in db.scalars(select(Course))}
    emps = emp_map(db, {r.employee_id for r in rows})
    return [_enrollment(r, courses, emps) for r in rows]


@router.patch("/enrollments/{enrollment_id}")
def update_enrollment(enrollment_id: uuid.UUID, body: EnrollmentPatch, ctx: AuthContext = Depends(get_tenant_ctx),
                      db: Session = Depends(get_db)):
    e, me = db.get(Enrollment, enrollment_id), me_of(db, ctx)
    if e is None or not ("training.manage" in ctx.permissions or (me is not None and me.id == e.employee_id)):
        raise NotFound("Enrollment not found")
    e.status = body.status
    e.completed_on = date.today() if body.status == "completed" else None
    db.commit()
    return {"id": e.id, "status": e.status, "completed_on": e.completed_on}
