from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import Forbidden, NotFound
from app.db.base import utcnow
from app.db.session import get_db
from app.modules.employees import service as emp_service
from app.modules.employees.models import Employee
from app.modules.identity.deps import AuthContext, check_origin, get_tenant_ctx, require
from app.modules.notifications import service
from app.modules.notifications.models import Notice, Notification, Task
from app.modules.tenancy import service as tenancy
from app.modules.tenancy.models import TenantMembership

router = APIRouter(tags=["notices"], dependencies=[Depends(check_origin)])


def _me(db: Session, ctx: AuthContext) -> Employee | None:
    return emp_service.current_employee(db, ctx.membership.id if ctx.membership else None)


# ------------------------------------------------------------------ notices
class NoticeIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=3, max_length=10000)
    branch_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None


def _notice(n: Notice, names: dict) -> dict:
    audience = "Everyone"
    if n.branch_id:
        audience = f"Branch: {names['branch'].get(n.branch_id, '?')}"
    elif n.department_id:
        audience = f"Department: {names['department'].get(n.department_id, '?')}"
    return {"id": n.id, "title": n.title, "body": n.body, "audience": audience, "branch_id": n.branch_id,
            "department_id": n.department_id, "published_at": n.published_at}


@router.get("/notices")
def list_notices(ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    stmt = select(Notice).order_by(Notice.published_at.desc()).limit(200)
    if "notices.manage" not in ctx.permissions:
        me = _me(db, ctx)
        conds = [Notice.branch_id.is_(None) & Notice.department_id.is_(None)]
        if me is not None:
            if me.branch_id:
                conds.append(Notice.branch_id == me.branch_id)
            if me.department_id:
                conds.append(Notice.department_id == me.department_id)
        stmt = stmt.where(or_(*conds))
    names = emp_service.name_maps(db)
    return [_notice(n, names) for n in db.scalars(stmt)]


@router.post("/notices", status_code=201)
def create_notice(body: NoticeIn, ctx: AuthContext = Depends(require("notices.manage")),
                  db: Session = Depends(get_db)):
    n = Notice(tenant_id=ctx.tenant.id, author_identity_id=ctx.identity.id, published_at=utcnow(),
               **body.model_dump())
    db.add(n)
    db.flush()
    stmt = select(Employee).where(Employee.deleted_at.is_(None), Employee.membership_id.is_not(None))
    if n.branch_id:
        stmt = stmt.where(Employee.branch_id == n.branch_id)
    if n.department_id:
        stmt = stmt.where(Employee.department_id == n.department_id)
    for emp in db.scalars(stmt):
        service.notify_employee(db, emp, "notice", n.title, n.body[:200], "/me/notices", dedupe_key=f"notice:{n.id}")
    tenancy.record_audit(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id, action="notice.published",
                         entity_type="notice", entity_id=n.id, ip=ctx.ip)
    db.commit()
    return _notice(n, emp_service.name_maps(db))


@router.delete("/notices/{notice_id}", status_code=204)
def delete_notice(notice_id: uuid.UUID, ctx: AuthContext = Depends(require("notices.manage")),
                  db: Session = Depends(get_db)):
    n = db.get(Notice, notice_id)
    if n is None:
        raise NotFound("Notice not found")
    db.delete(n)
    db.commit()


# ------------------------------------------------------------------ notifications
@router.get("/notifications")
def list_notifications(unread_only: bool = False, ctx: AuthContext = Depends(get_tenant_ctx),
                       db: Session = Depends(get_db)):
    base = select(Notification).where(Notification.membership_id == ctx.membership.id)
    unread = db.scalar(select(func.count()).select_from(Notification).where(
        Notification.membership_id == ctx.membership.id, Notification.read_at.is_(None))) or 0
    stmt = base.order_by(Notification.created_at.desc()).limit(50)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    return {"unread": unread, "items": [{"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "link": n.link,
                                         "created_at": n.created_at, "read": n.read_at is not None}
                                        for n in db.scalars(stmt)]}


@router.post("/notifications/read-all", status_code=204)
def read_all(ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    for n in db.scalars(select(Notification).where(Notification.membership_id == ctx.membership.id,
                                                   Notification.read_at.is_(None))):
        n.read_at = utcnow()
    db.commit()


@router.post("/notifications/{notification_id}/read", status_code=204)
def read_one(notification_id: uuid.UUID, ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    n = db.scalar(select(Notification).where(Notification.id == notification_id,
                                             Notification.membership_id == ctx.membership.id))
    if n is None:
        raise NotFound("Notification not found")
    n.read_at = n.read_at or utcnow()
    db.commit()


# ------------------------------------------------------------------ tasks
class TaskIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    assignee_id: uuid.UUID | None = None
    due_date: date | None = None
    priority: str = Field(default="normal", pattern="^(low|normal|high)$")


class TaskPatch(BaseModel):
    status: str | None = Field(default=None, pattern="^(todo|in_progress|blocked|done)$")
    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = None
    due_date: date | None = None
    priority: str | None = Field(default=None, pattern="^(low|normal|high)$")
    assignee_id: uuid.UUID | None = None


def _task(t: Task, emps: dict) -> dict:
    a = emps.get(t.assignee_id)
    return {"id": t.id, "title": t.title, "description": t.description, "assignee_id": t.assignee_id,
            "assignee": a.full_name if a else None, "due_date": t.due_date, "status": t.status,
            "priority": t.priority, "completed_at": t.completed_at,
            "overdue": bool(t.due_date and t.due_date < date.today() and t.status != "done")}


@router.get("/tasks")
def list_tasks(scope: str = Query("mine", pattern="^(mine|team)$"), assignee_id: uuid.UUID | None = None,
               ctx: AuthContext = Depends(get_tenant_ctx),
               db: Session = Depends(get_db)):
    me = _me(db, ctx)
    stmt = select(Task).order_by(Task.status, Task.due_date.is_(None), Task.due_date)
    if scope == "team":
        if "tasks.manage" not in ctx.permissions:
            raise Forbidden("You do not have permission", code="permission_denied")
        if "employees.read" not in ctx.permissions:
            stmt = stmt.where(Task.assignee_id.in_(emp_service.team_ids(db, me.id) if me else set()))
    else:
        if me is None:
            return []
        stmt = stmt.where(Task.assignee_id == me.id)
    if assignee_id:
        stmt = stmt.where(Task.assignee_id == assignee_id)
    rows = db.scalars(stmt.limit(300)).all()
    emps = {e.id: e for e in db.scalars(select(Employee).where(Employee.id.in_({t.assignee_id for t in rows})))}
    return [_task(t, emps) for t in rows]


@router.post("/tasks", status_code=201)
def create_task(body: TaskIn, ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    me = _me(db, ctx)
    target_id = body.assignee_id or (me.id if me else None)
    if target_id is None:
        raise NotFound("No employee record is linked to your account")
    if me is None or target_id != me.id:
        if "tasks.manage" not in ctx.permissions:
            raise Forbidden("You can only create tasks for yourself", code="permission_denied")
        if "employees.read" not in ctx.permissions and (me is None or target_id not in emp_service.team_ids(db, me.id)):
            raise NotFound("Employee not found")
    assignee = emp_service.get_employee(db, target_id)
    t = Task(tenant_id=ctx.tenant.id, title=body.title.strip(), description=body.description,
             assignee_id=assignee.id, created_by=ctx.identity.id, due_date=body.due_date, priority=body.priority)
    db.add(t)
    if me is None or assignee.id != me.id:
        service.notify_employee(db, assignee, "task", f"New task: {t.title}", None, "/me/tasks")
    db.commit()
    return _task(t, {assignee.id: assignee})


@router.patch("/tasks/{task_id}")
def update_task(task_id: uuid.UUID, body: TaskPatch, ctx: AuthContext = Depends(get_tenant_ctx),
                db: Session = Depends(get_db)):
    t = db.get(Task, task_id)
    me = _me(db, ctx)
    if t is None:
        raise NotFound("Task not found")
    mine = me is not None and t.assignee_id == me.id
    if not mine and "tasks.manage" not in ctx.permissions:
        raise NotFound("Task not found")
    changes = body.model_dump(exclude_unset=True)
    old_status, old_assignee_id = t.status, t.assignee_id
    changed_fields = {key for key, value in changes.items() if getattr(t, key) != value}
    if "assignee_id" in changes:
        if "tasks.manage" not in ctx.permissions or changes["assignee_id"] is None:
            raise Forbidden("You cannot reassign this task", code="permission_denied")
        assignee = emp_service.get_employee(db, changes["assignee_id"])
        if "employees.read" not in ctx.permissions and (me is None or assignee.id not in emp_service.team_ids(db, me.id)):
            raise NotFound("Employee not found")
    for k, v in changes.items():
        setattr(t, k, v)
    if changes.get("status") == "done":
        t.completed_at = utcnow()
    elif "status" in changes:
        t.completed_at = None
    if t.assignee_id != old_assignee_id:
        service.notify_employee(db, emp_service.get_employee(db, t.assignee_id), "task",
                                f"Task assigned to you: {t.title}", "Open your board to review it.", "/me/tasks")
        old_assignee = emp_service.get_employee(db, old_assignee_id)
        if me is None or old_assignee.id != me.id:
            service.notify_employee(db, old_assignee, "task", f"Task reassigned: {t.title}",
                                    "This task is no longer assigned to you.", "/me/tasks")
    elif t.status != old_status:
        assignee = emp_service.get_employee(db, t.assignee_id)
        if me is None or assignee.id != me.id:
            service.notify_employee(db, assignee, "task", f"Task moved to {t.status.replace('_', ' ')}: {t.title}",
                                    None, "/me/tasks")
    elif changed_fields:
        assignee = emp_service.get_employee(db, t.assignee_id)
        if me is None or assignee.id != me.id:
            service.notify_employee(db, assignee, "task", f"Task details updated: {t.title}", None, "/me/tasks")
    if changed_fields and t.created_by != ctx.identity.id and t.created_by:
        creator = db.scalar(select(TenantMembership).where(TenantMembership.tenant_id == ctx.tenant.id,
                                                            TenantMembership.identity_id == t.created_by))
        if creator and creator.id != emp_service.get_employee(db, t.assignee_id).membership_id:
            service.notify_membership(db, ctx.tenant.id, creator.id, "task",
                                      f"Task updated: {t.title}", f"Status: {t.status.replace('_', ' ')}", "/tasks")
    db.commit()
    return _task(t, {e.id: e for e in db.scalars(select(Employee).where(Employee.id == t.assignee_id))})


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: uuid.UUID, ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    t = db.get(Task, task_id)
    me = _me(db, ctx)
    if t is None or not (("tasks.manage" in ctx.permissions) or (me is not None and t.assignee_id == me.id
                                                                 and t.created_by == ctx.identity.id)):
        raise NotFound("Task not found")
    assignee = emp_service.get_employee(db, t.assignee_id)
    if me is None or assignee.id != me.id:
        service.notify_employee(db, assignee, "task", f"Task removed: {t.title}", None, "/me/tasks")
    db.delete(t)
    db.commit()
