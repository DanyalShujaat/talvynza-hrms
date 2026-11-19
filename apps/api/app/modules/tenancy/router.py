from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.core.pagination import Page, PageParams
from app.db.session import get_db
from app.modules.identity.deps import AuthContext, check_origin, get_auth, require
from app.modules.tenancy import service
from app.modules.tenancy.permissions import CATALOG

router = APIRouter(tags=["organization"], dependencies=[Depends(check_origin)])


class OrgCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    country: str = Field(min_length=2, max_length=2)
    currency: str = Field(min_length=3, max_length=3)
    timezone: str
    legal_name: str | None = Field(default=None, max_length=250)
    expected_employee_count: int | None = Field(default=None, ge=1, le=1_000_000)


class OrgUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    legal_name: str | None = Field(default=None, max_length=250)
    timezone: str | None = None
    expected_employee_count: int | None = Field(default=None, ge=1, le=1_000_000)


class InviteIn(BaseModel):
    email: EmailStr
    role_key: str = Field(max_length=60)


class AcceptInviteIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class MemberRolesIn(BaseModel):
    role_keys: list[str] = Field(min_length=1, max_length=20)


class RoleCreateIn(BaseModel):
    key: str
    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    permissions: list[str] = Field(default_factory=list)


class RolePermsIn(BaseModel):
    permissions: list[str]


class AuditOut(BaseModel):
    id: uuid.UUID
    actor_identity_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: str | None
    details: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


def _org(t) -> dict:
    return {"id": t.id, "name": t.name, "legal_name": t.legal_name, "slug": t.slug, "country": t.country,
            "currency": t.currency, "timezone": t.timezone, "status": t.status, "plan_code": t.plan_code,
            "trial_ends_at": t.trial_ends_at, "employee_capacity": t.employee_capacity,
            "expected_employee_count": t.expected_employee_count, "enabled_modules": t.enabled_modules,
            "onboarding_state": t.onboarding_state}


@router.post("/organizations", status_code=201)
def create_organization(body: OrgCreateIn, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    """Any verified identity may create an additional organization (becomes its owner)."""
    t = service.create_tenant(db, ctx.identity, name=body.name, country=body.country, currency=body.currency,
                              timezone=body.timezone, legal_name=body.legal_name,
                              expected_employee_count=body.expected_employee_count, ip=ctx.ip)
    return _org(t)


@router.get("/organization")
def get_organization(ctx: AuthContext = Depends(require("org.read"))):
    return _org(ctx.tenant)


@router.patch("/organization")
def update_organization(body: OrgUpdateIn, ctx: AuthContext = Depends(require("org.manage")),
                        db: Session = Depends(get_db)):
    t = ctx.tenant
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if "timezone" in changes:
        service._validate_org_inputs(t.country, t.currency, changes["timezone"])
    for k, v in changes.items():
        setattr(t, k, v)
    service.record_audit(db, tenant_id=t.id, actor=ctx.identity.id, action="tenant.updated", entity_type="tenant",
                         entity_id=t.id, details={"fields": sorted(changes)}, ip=ctx.ip)
    db.commit()
    return _org(t)


@router.get("/members")
def members(params: PageParams = Depends(), ctx: AuthContext = Depends(require("members.read")),
            db: Session = Depends(get_db)):
    items, total = service.list_members(db, ctx.tenant.id, params)
    return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}


@router.put("/members/{membership_id}/roles")
def set_member_roles(membership_id: uuid.UUID, body: MemberRolesIn,
                     ctx: AuthContext = Depends(require("members.manage")), db: Session = Depends(get_db)):
    roles = service.set_member_roles(db, tenant_id=ctx.tenant.id, actor=ctx.identity, actor_perms=ctx.permissions,
                                     membership_id=membership_id, role_keys=body.role_keys, ip=ctx.ip)
    return {"roles": roles}


@router.delete("/members/{membership_id}", status_code=204)
def remove_member(membership_id: uuid.UUID, ctx: AuthContext = Depends(require("members.manage")),
                  db: Session = Depends(get_db)):
    service.remove_member(db, tenant_id=ctx.tenant.id, actor=ctx.identity, membership_id=membership_id, ip=ctx.ip)


@router.post("/invitations", status_code=201)
def invite(body: InviteIn, ctx: AuthContext = Depends(require("members.manage")), db: Session = Depends(get_db)):
    service.invite_member(db, tenant=ctx.tenant, actor=ctx.identity, actor_perms=ctx.permissions,
                          email=body.email, role_key=body.role_key, ip=ctx.ip)
    return {"message": "Invitation sent"}


@router.post("/invitations/accept")
def accept(body: AcceptInviteIn, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    t = service.accept_invitation(db, ctx.identity, body.token, ip=ctx.ip)
    return {"tenant_id": t.id, "name": t.name}


@router.get("/permissions")
def permissions(ctx: AuthContext = Depends(require("roles.manage"))):
    return [{"code": c, "module": m, "description": d, "is_sensitive": s} for c, (m, d, s) in sorted(CATALOG.items())]


@router.get("/roles")
def roles(ctx: AuthContext = Depends(require("members.read")), db: Session = Depends(get_db)):
    return service.list_roles(db)


@router.post("/roles", status_code=201)
def create_role(body: RoleCreateIn, ctx: AuthContext = Depends(require("roles.manage")),
                db: Session = Depends(get_db)):
    r = service.create_custom_role(db, tenant_id=ctx.tenant.id, actor=ctx.identity, actor_perms=ctx.permissions,
                                   key=body.key, name=body.name, description=body.description,
                                   permissions=body.permissions, ip=ctx.ip)
    return {"id": r.id, "key": r.key}


@router.put("/roles/{role_id}/permissions")
def set_role_permissions(role_id: uuid.UUID, body: RolePermsIn, ctx: AuthContext = Depends(require("roles.manage")),
                         db: Session = Depends(get_db)):
    r = service.set_role_permissions(db, tenant_id=ctx.tenant.id, actor=ctx.identity, actor_perms=ctx.permissions,
                                     role_id=role_id, permissions=body.permissions, ip=ctx.ip)
    return {"id": r.id, "permissions": sorted(set(body.permissions))}


@router.get("/audit-logs", response_model=Page[AuditOut])
def audit_logs(action: str | None = None, params: PageParams = Depends(),
               ctx: AuthContext = Depends(require("audit.read")), db: Session = Depends(get_db)):
    rows, total = service.list_audit_logs(db, params, action)
    return Page[AuditOut](items=[AuditOut.model_validate(r) for r in rows], total=total, page=params.page,
                          page_size=params.page_size)
