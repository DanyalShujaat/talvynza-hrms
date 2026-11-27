from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.db.base import utcnow
from app.db.session import get_db
from app.modules.common import audit, emp_map, in_team, me_of, need_any, need_me
from app.modules.employees import service as emp_service
from app.modules.employees.models import LIVE_STATUSES, Employee
from app.modules.identity.deps import AuthContext, check_origin, get_tenant_ctx, require
from app.modules.notifications.service import notify_employee
from app.modules.performance.models import Goal, Review, ReviewCycle

router = APIRouter(tags=["performance"], dependencies=[Depends(check_origin)])


class GoalIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    due_date: date | None = None
    employee_id: uuid.UUID | None = None


class GoalPatch(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = None
    due_date: date | None = None
    progress: int | None = Field(default=None, ge=0, le=100)
    status: str | None = Field(default=None, pattern="^(active|achieved|dropped)$")


class CycleIn(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    period_start: date
    period_end: date


class AssessmentIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(min_length=3, max_length=5000)


# ------------------------------------------------------------------ goals
def _goal(g: Goal, emps: dict) -> dict:
    e = emps.get(g.employee_id)
    return {"id": g.id, "employee_id": g.employee_id, "employee": e.full_name if e else None, "title": g.title,
            "description": g.description, "due_date": g.due_date, "progress": g.progress, "status": g.status,
            "overdue": bool(g.due_date and g.due_date < date.today() and g.status == "active")}


def _can_manage_goal(db: Session, ctx: AuthContext, me: Employee | None, employee_id: uuid.UUID) -> bool:
    if "performance.manage" in ctx.permissions:
        return True
    return "performance.review_team" in ctx.permissions and in_team(db, me, employee_id)


@router.get("/goals")
def list_goals(scope: str = Query("mine", pattern="^(mine|team|all)$"), employee_id: uuid.UUID | None = None,
               ctx: AuthContext = Depends(get_tenant_ctx),
               db: Session = Depends(get_db)):
    me = me_of(db, ctx)
    stmt = select(Goal).order_by(Goal.status, Goal.due_date.is_(None), Goal.due_date)
    if scope == "all":
        need_any(ctx, "performance.manage")
    elif scope == "team":
        need_any(ctx, "performance.review_team")
        stmt = stmt.where(Goal.employee_id.in_((emp_service.team_ids(db, me.id) - {me.id}) if me else set()))
    else:
        if me is None:
            return []
        stmt = stmt.where(Goal.employee_id == me.id)
    if employee_id:
        stmt = stmt.where(Goal.employee_id == employee_id)
    rows = db.scalars(stmt.limit(500)).all()
    emps = emp_map(db, {g.employee_id for g in rows})
    return [_goal(g, emps) for g in rows]


@router.post("/goals", status_code=201)
def create_goal(body: GoalIn, ctx: AuthContext = Depends(require("performance.read_own")), db: Session = Depends(get_db)):
    me = need_me(db, ctx)
    target = body.employee_id or me.id
    if target != me.id and not _can_manage_goal(db, ctx, me, target):
        raise NotFound("Employee not found")
    emp = emp_service.get_employee(db, target)
    g = Goal(tenant_id=ctx.tenant.id, employee_id=emp.id, title=body.title.strip(), description=body.description,
             due_date=body.due_date, created_by=ctx.identity.id)
    db.add(g)
    if emp.id != me.id:
        notify_employee(db, emp, "goal", f"New goal: {g.title}", None, "/me/performance")
    db.commit()
    return _goal(g, {emp.id: emp})


def _load_goal(db: Session, ctx: AuthContext, goal_id: uuid.UUID) -> Goal:
    g, me = db.get(Goal, goal_id), me_of(db, ctx)
    if g is None or not ((me is not None and me.id == g.employee_id) or _can_manage_goal(db, ctx, me, g.employee_id)):
        raise NotFound("Goal not found")
    return g


@router.patch("/goals/{goal_id}")
def update_goal(goal_id: uuid.UUID, body: GoalPatch, ctx: AuthContext = Depends(get_tenant_ctx),
                db: Session = Depends(get_db)):
    g = _load_goal(db, ctx, goal_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(g, k, v)
    if g.progress == 100 and g.status == "active":
        g.status = "achieved"
    db.commit()
    return _goal(g, emp_map(db, {g.employee_id}))


@router.delete("/goals/{goal_id}", status_code=204)
def delete_goal(goal_id: uuid.UUID, ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    db.delete(_load_goal(db, ctx, goal_id))
    db.commit()


# ------------------------------------------------------------------ review cycles
def _cycle(c: ReviewCycle, counts: dict) -> dict:
    total, done = counts.get(c.id, (0, 0))
    return {"id": c.id, "name": c.name, "period_start": c.period_start, "period_end": c.period_end,
            "status": c.status, "reviews": total, "completed": done}


def _counts(db: Session) -> dict:
    out: dict = {}
    for cid, status, n in db.execute(select(Review.cycle_id, Review.status, func.count())
                                     .group_by(Review.cycle_id, Review.status)).all():
        total, done = out.get(cid, (0, 0))
        out[cid] = (total + n, done + (n if status == "completed" else 0))
    return out


@router.get("/review-cycles")
def list_cycles(ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    need_any(ctx, "performance.manage", "performance.review_team", "performance.read_own")
    counts = _counts(db)
    return [_cycle(c, counts) for c in db.scalars(select(ReviewCycle).order_by(ReviewCycle.period_end.desc()))]


@router.post("/review-cycles", status_code=201)
def create_cycle(body: CycleIn, ctx: AuthContext = Depends(require("performance.manage")), db: Session = Depends(get_db)):
    if body.period_end < body.period_start:
        raise ValidationFailed("The period end is before its start", code="bad_period")
    if db.scalar(select(ReviewCycle.id).where(func.lower(ReviewCycle.name) == body.name.lower())):
        raise Conflict("A review cycle with this name exists", code="duplicate_name")
    c = ReviewCycle(tenant_id=ctx.tenant.id, **body.model_dump())
    db.add(c)
    db.commit()
    return _cycle(c, {})


@router.post("/review-cycles/{cycle_id}/launch")
def launch(cycle_id: uuid.UUID, ctx: AuthContext = Depends(require("performance.manage")), db: Session = Depends(get_db)):
    """Creates one review per current employee. The reviewer is the employee's manager at launch."""
    c = db.get(ReviewCycle, cycle_id)
    if c is None:
        raise NotFound("Review cycle not found")
    if c.status != "draft":
        raise Conflict("This cycle has already been launched", code="invalid_state")
    created = 0
    for emp in db.scalars(select(Employee).where(Employee.deleted_at.is_(None), Employee.status.in_(LIVE_STATUSES))):
        db.add(Review(tenant_id=ctx.tenant.id, cycle_id=c.id, employee_id=emp.id, reviewer_id=emp.manager_id))
        notify_employee(db, emp, "review", f"{c.name}: your self-assessment is open", None, "/me/performance",
                        dedupe_key=f"review:{c.id}")
        created += 1
    c.status = "active"
    audit(db, ctx, "review_cycle.launched", "review_cycle", c.id, {"reviews": created})
    db.commit()
    return _cycle(c, _counts(db))


@router.post("/review-cycles/{cycle_id}/close")
def close_cycle(cycle_id: uuid.UUID, ctx: AuthContext = Depends(require("performance.manage")),
                db: Session = Depends(get_db)):
    c = db.get(ReviewCycle, cycle_id)
    if c is None:
        raise NotFound("Review cycle not found")
    if c.status != "active":
        raise Conflict("Only an active cycle can be closed", code="invalid_state")
    c.status = "closed"
    audit(db, ctx, "review_cycle.closed", "review_cycle", c.id)
    db.commit()
    return _cycle(c, _counts(db))


# ------------------------------------------------------------------ reviews
def _review(r: Review, emps: dict, cycles: dict, viewer_is_subject: bool) -> dict:
    e, rv = emps.get(r.employee_id), emps.get(r.reviewer_id)
    show_manager = r.status == "completed" or not viewer_is_subject
    return {"id": r.id, "cycle_id": r.cycle_id, "cycle": cycles.get(r.cycle_id), "employee_id": r.employee_id,
            "employee": e.full_name if e else None, "reviewer": rv.full_name if rv else None, "status": r.status,
            "self_rating": r.self_rating, "self_comment": r.self_comment,
            "manager_rating": r.manager_rating if show_manager else None,
            "manager_comment": r.manager_comment if show_manager else None}


@router.get("/reviews")
def list_reviews(scope: str = Query("mine", pattern="^(mine|team|all)$"), cycle_id: uuid.UUID | None = None,
                 employee_id: uuid.UUID | None = None,
                 ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    me = me_of(db, ctx)
    stmt = select(Review).order_by(Review.created_at.desc())
    if scope == "all":
        need_any(ctx, "performance.manage")
    elif scope == "team":
        need_any(ctx, "performance.review_team")
        stmt = stmt.where(Review.reviewer_id == (me.id if me else None))
    else:
        if me is None:
            return []
        stmt = stmt.where(Review.employee_id == me.id)
    if cycle_id:
        stmt = stmt.where(Review.cycle_id == cycle_id)
    if employee_id:
        stmt = stmt.where(Review.employee_id == employee_id)
    rows = db.scalars(stmt.limit(500)).all()
    emps = emp_map(db, {r.employee_id for r in rows} | {r.reviewer_id for r in rows})
    cycles = {c.id: c.name for c in db.scalars(select(ReviewCycle))}
    return [_review(r, emps, cycles, me is not None and me.id == r.employee_id) for r in rows]


def _active_review(db: Session, review_id: uuid.UUID) -> Review:
    r = db.get(Review, review_id)
    if r is None:
        raise NotFound("Review not found")
    cycle = db.get(ReviewCycle, r.cycle_id)
    if cycle is None or cycle.status != "active":
        raise Conflict("This review cycle is closed", code="cycle_closed")
    return r


@router.post("/reviews/{review_id}/self")
def self_assessment(review_id: uuid.UUID, body: AssessmentIn, ctx: AuthContext = Depends(get_tenant_ctx),
                    db: Session = Depends(get_db)):
    me = need_me(db, ctx)
    r = db.get(Review, review_id)
    if r is None or r.employee_id != me.id:
        raise NotFound("Review not found")
    r = _active_review(db, review_id)
    if r.status != "pending_self":
        raise Conflict("Your self-assessment has already been submitted", code="invalid_state")
    r.self_rating, r.self_comment, r.status = body.rating, body.comment, "pending_manager"
    if r.reviewer_id:
        notify_employee(db, db.get(Employee, r.reviewer_id), "review", f"{me.full_name} submitted a self-assessment",
                        None, "/performance")
    db.commit()
    return {"id": r.id, "status": r.status}


@router.post("/reviews/{review_id}/manager")
def manager_assessment(review_id: uuid.UUID, body: AssessmentIn, ctx: AuthContext = Depends(get_tenant_ctx),
                       db: Session = Depends(get_db)):
    me = me_of(db, ctx)
    r = db.get(Review, review_id)
    is_reviewer = r is not None and me is not None and r.reviewer_id == me.id and "performance.review_team" in ctx.permissions
    if r is None or not (is_reviewer or "performance.manage" in ctx.permissions):
        raise NotFound("Review not found")
    if me is not None and me.id == r.employee_id:
        raise Forbidden("You cannot complete your own review", code="self_approval")
    r = _active_review(db, review_id)
    if r.status == "completed":
        raise Conflict("This review is already completed", code="invalid_state")
    if r.status == "pending_self":
        raise Conflict("The employee has not submitted a self-assessment yet", code="awaiting_self")
    r.manager_rating, r.manager_comment, r.status, r.completed_at = body.rating, body.comment, "completed", utcnow()
    notify_employee(db, emp_service.get_employee(db, r.employee_id), "review", "Your performance review is complete",
                    None, "/me/performance")
    audit(db, ctx, "review.completed", "review", r.id)
    db.commit()
    return {"id": r.id, "status": r.status}
