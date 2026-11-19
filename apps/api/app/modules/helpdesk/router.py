from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.db.base import utcnow
from app.db.session import get_db
from app.modules.common import audit, emp_map, me_of, need_any, need_me
from app.modules.employees import service as emp_service
from app.modules.helpdesk.models import CATEGORIES, SLA_HOURS, Ticket, TicketComment
from app.modules.identity.deps import AuthContext, check_origin, get_tenant_ctx, require
from app.modules.notifications.service import notify_employee, notify_permission_holders

router = APIRouter(prefix="/tickets", tags=["help desk"], dependencies=[Depends(check_origin)])
PRIORITY = "^(low|normal|high|urgent)$"


class TicketIn(BaseModel):
    category: str
    priority: str = Field(default="normal", pattern=PRIORITY)
    subject: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=3, max_length=5000)


class TicketPatch(BaseModel):
    status: str | None = Field(default=None, pattern="^(open|in_progress|resolved|closed)$")
    priority: str | None = Field(default=None, pattern=PRIORITY)
    assignee_id: uuid.UUID | None = None


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    internal: bool = False


class RatingIn(BaseModel):
    rating: int = Field(ge=1, le=5)


def _ticket(t: Ticket, emps: dict) -> dict:
    e, a = emps.get(t.employee_id), emps.get(t.assignee_id)
    open_ = t.status in ("open", "in_progress")
    return {"id": t.id, "number": t.number, "employee_id": t.employee_id, "employee": e.full_name if e else None,
            "category": t.category, "priority": t.priority, "subject": t.subject, "description": t.description,
            "status": t.status, "assignee_id": t.assignee_id, "assignee": a.full_name if a else None,
            "due_at": t.due_at, "overdue": open_ and t.due_at < utcnow(), "resolved_at": t.resolved_at,
            "rating": t.rating, "created_at": t.created_at}


@router.get("/categories")
def categories(ctx: AuthContext = Depends(get_tenant_ctx)):
    return list(CATEGORIES)


@router.post("", status_code=201)
def create(body: TicketIn, ctx: AuthContext = Depends(require("helpdesk.submit")), db: Session = Depends(get_db)):
    me = need_me(db, ctx)
    if body.category not in CATEGORIES:
        raise ValidationFailed("Unknown category", details=list(CATEGORIES))
    number = (db.scalar(select(func.max(Ticket.number))) or 1000) + 1
    t = Ticket(tenant_id=ctx.tenant.id, number=number, employee_id=me.id, status="open",
               due_at=utcnow() + timedelta(hours=SLA_HOURS[body.priority]), **body.model_dump())
    db.add(t)
    db.flush()
    notify_permission_holders(db, ctx.tenant.id, "helpdesk.manage", "ticket",
                              f"New HR ticket from {me.full_name}", t.subject, f"/inbox/ticket/{t.id}",
                              dedupe_key=f"ticket-opened:{t.id}", exclude_identity_id=ctx.identity.id)
    db.commit()
    return _ticket(t, {me.id: me})


@router.get("")
def list_tickets(scope: str = Query("mine", pattern="^(mine|all)$"), status: str | None = None,
                 ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    me = me_of(db, ctx)
    stmt = select(Ticket).order_by(Ticket.created_at.desc()).limit(300)
    if scope == "all":
        need_any(ctx, "helpdesk.manage")
    else:
        if me is None:
            return []
        stmt = stmt.where(Ticket.employee_id == me.id)
    if status == "active":
        stmt = stmt.where(Ticket.status.in_(("open", "in_progress")))
    elif status:
        stmt = stmt.where(Ticket.status == status)
    rows = db.scalars(stmt).all()
    emps = emp_map(db, {r.employee_id for r in rows} | {r.assignee_id for r in rows})
    return [_ticket(t, emps) for t in rows]


def _load(db: Session, ctx: AuthContext, ticket_id: uuid.UUID) -> tuple[Ticket, bool, bool]:
    """Returns the ticket, whether the caller is its requester and whether the caller is help desk staff."""
    t = db.get(Ticket, ticket_id)
    me = me_of(db, ctx)
    own = t is not None and me is not None and me.id == t.employee_id
    staff = "helpdesk.manage" in ctx.permissions
    if t is None or not (own or staff):
        raise NotFound("Ticket not found")
    return t, own, staff


@router.get("/{ticket_id}")
def get_ticket(ticket_id: uuid.UUID, ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    t, _own, staff = _load(db, ctx, ticket_id)
    stmt = select(TicketComment).where(TicketComment.ticket_id == t.id).order_by(TicketComment.created_at)
    if not staff:
        stmt = stmt.where(TicketComment.internal.is_(False))  # internal notes never reach the requester
    out = _ticket(t, emp_map(db, {t.employee_id, t.assignee_id}))
    out["comments"] = [{"id": c.id, "author": c.author_name, "body": c.body, "internal": c.internal,
                        "created_at": c.created_at} for c in db.scalars(stmt)]
    return out


@router.post("/{ticket_id}/comments", status_code=201)
def comment(ticket_id: uuid.UUID, body: CommentIn, ctx: AuthContext = Depends(get_tenant_ctx),
            db: Session = Depends(get_db)):
    t, own, staff = _load(db, ctx, ticket_id)
    if t.status == "closed":
        raise Conflict("This ticket is closed", code="ticket_closed")
    internal = body.internal and staff
    db.add(TicketComment(tenant_id=ctx.tenant.id, ticket_id=t.id, author_identity_id=ctx.identity.id,
                         author_name=ctx.identity.full_name, body=body.body.strip(), internal=internal,
                         created_at=utcnow()))
    if staff and not own and not internal:
        notify_employee(db, emp_service.get_employee(db, t.employee_id), "ticket",
                        f"New reply on ticket #{t.number}", t.subject, f"/me/helpdesk/{t.id}")
    if own and t.status == "resolved":
        t.status, t.resolved_at = "in_progress", None  # the requester replied: reopen
    db.commit()
    return {"ok": True}


@router.patch("/{ticket_id}")
def update(ticket_id: uuid.UUID, body: TicketPatch, ctx: AuthContext = Depends(require("helpdesk.manage")),
           db: Session = Depends(get_db)):
    t, _own, _staff = _load(db, ctx, ticket_id)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("assignee_id"):
        emp_service.get_employee(db, changes["assignee_id"])
    if "priority" in changes and changes["priority"] != t.priority:
        t.due_at = t.created_at + timedelta(hours=SLA_HOURS[changes["priority"]])
    for k, v in changes.items():
        setattr(t, k, v)
    if changes.get("status") in ("resolved", "closed"):
        t.resolved_at = t.resolved_at or utcnow()
        notify_employee(db, emp_service.get_employee(db, t.employee_id), "ticket",
                        f"Ticket #{t.number} was {changes['status']}", t.subject, f"/me/helpdesk/{t.id}")
    elif "status" in changes:
        t.resolved_at = None
    audit(db, ctx, "ticket.updated", "ticket", t.id, {k: str(v) for k, v in changes.items()})
    db.commit()
    return _ticket(t, emp_map(db, {t.employee_id, t.assignee_id}))


@router.post("/{ticket_id}/close")
def close(ticket_id: uuid.UUID, ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    t, own, staff = _load(db, ctx, ticket_id)
    if t.status == "closed":
        raise Conflict("This ticket is already closed", code="ticket_closed")
    t.status, t.resolved_at = "closed", t.resolved_at or utcnow()
    db.commit()
    return {"id": t.id, "status": t.status}


@router.post("/{ticket_id}/rating")
def rate(ticket_id: uuid.UUID, body: RatingIn, ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    t, own, _staff = _load(db, ctx, ticket_id)
    if not own:
        raise NotFound("Ticket not found")
    if t.status not in ("resolved", "closed"):
        raise Conflict("You can rate a ticket once it is resolved", code="invalid_state")
    t.rating = body.rating
    db.commit()
    return {"id": t.id, "rating": t.rating}
