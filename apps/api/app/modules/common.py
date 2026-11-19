"""Helpers shared by the HR module routers."""
from __future__ import annotations

import uuid

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Forbidden, NotFound
from app.db.session import get_db
from app.modules.employees import service as emp_service
from app.modules.employees.models import Employee
from app.modules.identity.deps import AuthContext, get_tenant_ctx
from app.modules.tenancy import service as tenancy
from app.modules.tenancy.models import Tenant


def serialize_financial_writes(request: Request, ctx: AuthContext = Depends(get_tenant_ctx),
                               db: Session = Depends(get_db)) -> None:
    """One financial mutation per tenant at a time on PostgreSQL; held until commit/rollback."""
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        db.execute(select(Tenant.id).where(Tenant.id == ctx.tenant.id).with_for_update()).scalar_one()


def me_of(db: Session, ctx) -> Employee | None:
    return emp_service.current_employee(db, ctx.membership.id if ctx.membership else None)


def need_me(db: Session, ctx) -> Employee:
    me = me_of(db, ctx)
    if me is None:
        raise NotFound("No employee record is linked to your account")
    return me


def need_any(ctx, *perms: str) -> None:
    if not any(p in ctx.permissions for p in perms):
        raise Forbidden("You do not have permission to perform this action", code="permission_denied",
                        details=list(perms))


def in_team(db: Session, me: Employee | None, employee_id: uuid.UUID) -> bool:
    """True when employee_id reports to me, directly or indirectly. Never true for myself."""
    return me is not None and employee_id != me.id and employee_id in emp_service.team_ids(db, me.id)


def emp_map(db: Session, ids) -> dict[uuid.UUID, Employee]:
    ids = {i for i in ids if i is not None}
    return {e.id: e for e in db.scalars(select(Employee).where(Employee.id.in_(ids)))} if ids else {}


def audit(db: Session, ctx, action: str, entity_type: str, entity_id=None, details: dict | None = None) -> None:
    tenancy.record_audit(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id, action=action, entity_type=entity_type,
                         entity_id=entity_id, details=details, ip=ctx.ip)
