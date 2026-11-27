"""Tenancy business logic. Routers stay thin; everything transactional lives here."""
from __future__ import annotations

import re
import uuid
from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core import events
from app.core.config import get_settings
from app.core.email import send_email
from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.security import hash_token, new_token
from app.db.base import utcnow
from app.db.tenant_scope import ALL_TENANTS, tenant_scope
from app.modules.identity.models import Identity
from app.modules.tenancy.models import (
    AuditLog,
    Invitation,
    MembershipRole,
    Permission,
    Role,
    RolePermission,
    Tenant,
    TenantMembership,
)
from app.modules.tenancy.permissions import CATALOG, DEFAULT_ROLES

DEFAULT_TRIAL_MODULES = ["organization", "employees", "attendance", "leave", "payroll", "recruitment", "notices", "tasks"]


# ---------------------------------------------------------------- catalogue & audit
def sync_permission_catalog(db: Session) -> None:
    """Idempotently upsert the code-defined permission catalogue."""
    existing = {p.code: p for p in db.scalars(select(Permission))}
    for code, (module, desc, sensitive) in CATALOG.items():
        p = existing.get(code)
        if p is None:
            db.add(Permission(code=code, module=module, description=desc, is_sensitive=sensitive))
        else:
            p.module, p.description, p.is_sensitive = module, desc, sensitive
    db.commit()


def record_audit(
    db: Session, *, tenant_id: uuid.UUID, actor: uuid.UUID | None, action: str, entity_type: str,
    entity_id: str | uuid.UUID | None = None, details: dict | None = None, ip: str | None = None,
) -> None:
    with tenant_scope(db, tenant_id):
        db.add(AuditLog(
            tenant_id=tenant_id, actor_identity_id=actor, action=action, entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else None, details=details or {}, ip=ip, created_at=utcnow(),
        ))


# ---------------------------------------------------------------- tenant creation
def _validate_org_inputs(country: str, currency: str, tz: str) -> tuple[str, str]:
    if not re.fullmatch(r"[A-Za-z]{2}", country):
        raise ValidationFailed("Country must be an ISO 3166-1 alpha-2 code", details=[{"field": "country"}])
    if not re.fullmatch(r"[A-Za-z]{3}", currency):
        raise ValidationFailed("Currency must be an ISO 4217 code", details=[{"field": "currency"}])
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValidationFailed("Unknown time zone", details=[{"field": "timezone"}]) from None
    return country.upper(), currency.upper()


def _unique_slug(db: Session, name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "org"
    slug = base
    while db.scalar(select(func.count()).select_from(Tenant).where(Tenant.slug == slug)):
        slug = f"{base}-{uuid.uuid4().hex[:4]}"
    return slug


def seed_default_roles(db: Session, tenant_id: uuid.UUID) -> dict[str, Role]:
    """Create the default role set for a tenant. Caller must already be inside the tenant scope."""
    sync_permission_catalog(db)
    roles: dict[str, Role] = {}
    for key, (name, desc, perms) in DEFAULT_ROLES.items():
        role = Role(tenant_id=tenant_id, key=key, name=name, description=desc, is_system=True)
        db.add(role)
        db.flush()
        for code in sorted(perms):
            db.add(RolePermission(tenant_id=tenant_id, role_id=role.id, permission_code=code))
        roles[key] = role
    return roles


def sync_system_roles(db: Session) -> None:
    """Brings every tenant's default roles up to the current code definition. Only ever adds permissions, so a
    permission removed from a default role in code does not silently strip access from existing tenants."""
    for tenant_id in list(db.scalars(select(Tenant.id))):
        with tenant_scope(db, tenant_id):
            existing = {r.key: r for r in db.scalars(select(Role))}
            for key, (name, desc, perms) in DEFAULT_ROLES.items():
                role = existing.get(key)
                if role is None:
                    role = Role(tenant_id=tenant_id, key=key, name=name, description=desc, is_system=True)
                    db.add(role)
                    db.flush()
                have = set(db.scalars(select(RolePermission.permission_code).where(RolePermission.role_id == role.id)))
                for code in sorted(perms - have):
                    db.add(RolePermission(tenant_id=tenant_id, role_id=role.id, permission_code=code))
    db.commit()


def create_tenant(
    db: Session, owner: Identity, *, name: str, country: str, currency: str, timezone: str,
    legal_name: str | None = None, expected_employee_count: int | None = None, ip: str | None = None,
) -> Tenant:
    country, currency = _validate_org_inputs(country, currency, timezone)
    now = utcnow()
    tenant = Tenant(
        slug=_unique_slug(db, name), name=name.strip(), legal_name=legal_name, country=country,
        currency=currency, timezone=timezone, status="trialing", plan_code="trial",
        trial_ends_at=now + timedelta(days=get_settings().trial_days),
        expected_employee_count=expected_employee_count, enabled_modules=list(DEFAULT_TRIAL_MODULES),
        onboarding_state={"step": 1, "completed_steps": ["organization"]},
        created_by_identity_id=owner.id,
    )
    db.add(tenant)
    db.flush()
    membership = TenantMembership(tenant_id=tenant.id, identity_id=owner.id, status="active", joined_at=now)
    db.add(membership)
    db.flush()
    with tenant_scope(db, tenant.id):
        roles = seed_default_roles(db, tenant.id)
        db.add(MembershipRole(tenant_id=tenant.id, membership_id=membership.id, role_id=roles["owner"].id))
    record_audit(db, tenant_id=tenant.id, actor=owner.id, action="tenant.created", entity_type="tenant",
                 entity_id=tenant.id, details={"name": tenant.name}, ip=ip)
    db.commit()
    events.publish("tenant.created", {"db": db, "tenant_id": tenant.id, "owner": owner})
    return tenant


# ---------------------------------------------------------------- memberships
def list_identity_memberships(db: Session, identity_id: uuid.UUID) -> list[TenantMembership]:
    return list(db.scalars(
        select(TenantMembership).where(TenantMembership.identity_id == identity_id, TenantMembership.status == "active")
        .order_by(TenantMembership.joined_at)
    ))


def get_active_membership(db: Session, identity_id: uuid.UUID, tenant_id: uuid.UUID) -> TenantMembership | None:
    return db.scalar(select(TenantMembership).where(
        TenantMembership.identity_id == identity_id, TenantMembership.tenant_id == tenant_id,
        TenantMembership.status == "active"))


def permissions_for_membership(db: Session, membership_id: uuid.UUID) -> set[str]:
    """Caller must be inside the tenant scope."""
    rows = db.scalars(
        select(RolePermission.permission_code)
        .join(MembershipRole, MembershipRole.role_id == RolePermission.role_id)
        .where(MembershipRole.membership_id == membership_id)
    )
    return set(rows)


def role_keys_for_membership(db: Session, membership_id: uuid.UUID) -> list[str]:
    return list(db.scalars(
        select(Role.key).join(MembershipRole, MembershipRole.role_id == Role.id)
        .where(MembershipRole.membership_id == membership_id).order_by(Role.key)))


def _permissions_of_roles(db: Session, role_ids: list[uuid.UUID]) -> set[str]:
    return set(db.scalars(select(RolePermission.permission_code).where(RolePermission.role_id.in_(role_ids))))


def _assert_can_grant(db: Session, actor_perms: set[str], role_ids: list[uuid.UUID]) -> None:
    """Prevent privilege escalation: you can only hand out permissions you hold yourself."""
    excess = _permissions_of_roles(db, role_ids) - actor_perms
    if excess:
        raise Forbidden("You cannot grant permissions you do not hold", code="privilege_escalation",
                        details=sorted(excess))


def list_members(db: Session, tenant_id: uuid.UUID, params, membership_id: uuid.UUID | None = None):

    stmt = (select(TenantMembership, Identity)
            .join(Identity, Identity.id == TenantMembership.identity_id)
            .where(TenantMembership.tenant_id == tenant_id, TenantMembership.status != "removed")
            .order_by(Identity.full_name))
    if membership_id:
        stmt = stmt.where(TenantMembership.id == membership_id)
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.execute(stmt.limit(params.page_size).offset(params.offset)).all()
    out = [{"membership_id": m.id, "identity_id": i.id, "email": i.email, "full_name": i.full_name,
            "status": m.status, "roles": role_keys_for_membership(db, m.id)} for m, i in rows]
    return out, total


def set_member_roles(
    db: Session, *, tenant_id: uuid.UUID, actor: Identity, actor_perms: set[str], membership_id: uuid.UUID,
    role_keys: list[str], ip: str | None = None,
) -> list[str]:
    membership = db.scalar(select(TenantMembership).where(
        TenantMembership.id == membership_id, TenantMembership.tenant_id == tenant_id))
    if membership is None:
        raise NotFound("Member not found")
    roles = list(db.scalars(select(Role).where(Role.key.in_(role_keys))))
    if len(roles) != len(set(role_keys)):
        raise ValidationFailed("Unknown role key")
    if not roles:
        raise ValidationFailed("At least one role is required")
    _assert_can_grant(db, actor_perms, [r.id for r in roles])

    owner_role = db.scalar(select(Role).where(Role.key == "owner"))
    had_owner = db.scalar(select(func.count()).select_from(MembershipRole).where(
        MembershipRole.membership_id == membership_id, MembershipRole.role_id == owner_role.id))
    will_have_owner = any(r.key == "owner" for r in roles)
    if had_owner and not will_have_owner:
        owners = db.scalar(select(func.count()).select_from(MembershipRole).join(
            TenantMembership, TenantMembership.id == MembershipRole.membership_id).where(
            MembershipRole.role_id == owner_role.id, TenantMembership.status == "active"))
        if owners <= 1:
            raise Conflict("An organization must keep at least one owner", code="last_owner")

    for mr in db.scalars(select(MembershipRole).where(MembershipRole.membership_id == membership_id)):
        db.delete(mr)
    db.flush()
    for r in roles:
        db.add(MembershipRole(tenant_id=tenant_id, membership_id=membership_id, role_id=r.id))
    record_audit(db, tenant_id=tenant_id, actor=actor.id, action="member.roles_changed", entity_type="membership",
                 entity_id=membership_id, details={"roles": sorted(role_keys)}, ip=ip)
    db.commit()
    return sorted(role_keys)


# ---------------------------------------------------------------- custom roles
def create_custom_role(
    db: Session, *, tenant_id: uuid.UUID, actor: Identity, actor_perms: set[str], key: str, name: str,
    description: str | None, permissions: list[str], ip: str | None = None,
) -> Role:
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,59}", key):
        raise ValidationFailed("Role key must be snake_case, 3-60 chars")
    unknown = set(permissions) - set(CATALOG)
    if unknown:
        raise ValidationFailed("Unknown permissions", details=sorted(unknown))
    excess = set(permissions) - actor_perms
    if excess:
        raise Forbidden("You cannot grant permissions you do not hold", code="privilege_escalation",
                        details=sorted(excess))
    if db.scalar(select(func.count()).select_from(Role).where(Role.key == key)):
        raise Conflict("A role with this key already exists")
    role = Role(tenant_id=tenant_id, key=key, name=name, description=description, is_system=False)
    db.add(role)
    db.flush()
    for code in sorted(set(permissions)):
        db.add(RolePermission(tenant_id=tenant_id, role_id=role.id, permission_code=code))
    record_audit(db, tenant_id=tenant_id, actor=actor.id, action="role.created", entity_type="role",
                 entity_id=role.id, details={"key": key, "permissions": sorted(set(permissions))}, ip=ip)
    db.commit()
    return role


def set_role_permissions(
    db: Session, *, tenant_id: uuid.UUID, actor: Identity, actor_perms: set[str], role_id: uuid.UUID,
    permissions: list[str], ip: str | None = None,
) -> Role:
    role = db.get(Role, role_id)
    if role is None:
        raise NotFound("Role not found")
    if role.is_system:
        raise Forbidden("System roles cannot be modified; clone them into a custom role", code="system_role")
    unknown = set(permissions) - set(CATALOG)
    if unknown:
        raise ValidationFailed("Unknown permissions", details=sorted(unknown))
    excess = set(permissions) - actor_perms
    if excess:
        raise Forbidden("You cannot grant permissions you do not hold", code="privilege_escalation",
                        details=sorted(excess))
    for rp in db.scalars(select(RolePermission).where(RolePermission.role_id == role_id)):
        db.delete(rp)
    db.flush()
    for code in sorted(set(permissions)):
        db.add(RolePermission(tenant_id=tenant_id, role_id=role_id, permission_code=code))
    record_audit(db, tenant_id=tenant_id, actor=actor.id, action="role.permissions_changed", entity_type="role",
                 entity_id=role_id, details={"permissions": sorted(set(permissions))}, ip=ip)
    db.commit()
    return role


def list_roles(db: Session) -> list[dict]:
    out = []
    for r in db.scalars(select(Role).order_by(Role.is_system.desc(), Role.name)):
        perms = sorted(db.scalars(select(RolePermission.permission_code).where(RolePermission.role_id == r.id)))
        out.append({"id": r.id, "key": r.key, "name": r.name, "description": r.description,
                    "is_system": r.is_system, "permissions": perms})
    return out


# ---------------------------------------------------------------- invitations
def invite_member(
    db: Session, *, tenant: Tenant, actor: Identity, actor_perms: set[str], email: str, role_key: str,
    ip: str | None = None,
) -> None:
    email = email.strip().lower()
    role = db.scalar(select(Role).where(Role.key == role_key))
    if role is None:
        raise ValidationFailed("Unknown role key")
    _assert_can_grant(db, actor_perms, [role.id])
    token = new_token()
    db.add(Invitation(
        tenant_id=tenant.id, email=email, role_key=role_key, token_hash=hash_token(token), invited_by=actor.id,
        expires_at=utcnow() + timedelta(days=7), created_at=utcnow()))
    record_audit(db, tenant_id=tenant.id, actor=actor.id, action="member.invited", entity_type="invitation",
                 details={"email": email, "role": role_key}, ip=ip)
    db.commit()
    link = f"{get_settings().frontend_url}/accept-invitation?token={token}"
    send_email(email, f"Invitation to join {tenant.name} on Talvynza HRMS",
               f"{actor.full_name} invited you to join {tenant.name}.\n\nSet your password and sign in: {link}\n\n"
               "The link expires in 7 days.")


def accept_invitation(db: Session, identity: Identity, token: str, ip: str | None = None) -> Tenant:
    with tenant_scope(db, ALL_TENANTS):  # explicit system context: the invitee has no tenant yet
        inv = db.scalar(select(Invitation).where(Invitation.token_hash == hash_token(token)))
        if inv is None or inv.accepted_at is not None or inv.expires_at < utcnow():
            raise NotFound("Invitation is invalid or has expired")
        if inv.email != identity.email:
            raise Forbidden("This invitation was issued to a different email address")
        tenant = db.get(Tenant, inv.tenant_id)
        if tenant is None or tenant.status not in ("trialing", "active"):
            raise Conflict("This organization is not accepting new members")
        tenant_id = inv.tenant_id
        role_key = inv.role_key
        inv.accepted_at = utcnow()
    membership = db.scalar(select(TenantMembership).where(
        TenantMembership.tenant_id == tenant_id, TenantMembership.identity_id == identity.id))
    if membership is None:
        membership = TenantMembership(tenant_id=tenant_id, identity_id=identity.id, status="active",
                                      joined_at=utcnow())
        db.add(membership)
    else:
        membership.status = "active"
    db.flush()
    with tenant_scope(db, tenant_id):
        role = db.scalar(select(Role).where(Role.key == role_key))
        for mr in db.scalars(select(MembershipRole).where(MembershipRole.membership_id == membership.id)):
            db.delete(mr)
        db.flush()
        db.add(MembershipRole(tenant_id=tenant_id, membership_id=membership.id, role_id=role.id))
    record_audit(db, tenant_id=tenant_id, actor=identity.id, action="member.joined", entity_type="membership",
                 entity_id=membership.id, ip=ip)
    db.commit()
    events.publish("member.joined", {"db": db, "tenant_id": tenant_id, "membership_id": membership.id,
                                     "email": identity.email})
    return tenant


def remove_member(db: Session, *, tenant_id: uuid.UUID, actor: Identity, membership_id: uuid.UUID,
                  ip: str | None = None) -> None:
    """Revokes access to the organization. The employee record and its history stay."""
    from app.modules.employees.models import Employee
    from app.modules.identity.models import AuthSession

    m = db.scalar(select(TenantMembership).where(TenantMembership.id == membership_id,
                                                 TenantMembership.tenant_id == tenant_id,
                                                 TenantMembership.status != "removed"))
    if m is None:
        raise NotFound("Member not found")
    if m.identity_id == actor.id:
        raise Conflict("You cannot remove your own access", code="cannot_remove_self")
    owner_role = db.scalar(select(Role).where(Role.key == "owner"))
    if db.scalar(select(func.count()).select_from(MembershipRole).where(
            MembershipRole.membership_id == m.id, MembershipRole.role_id == owner_role.id)):
        owners = db.scalar(select(func.count()).select_from(MembershipRole).join(
            TenantMembership, TenantMembership.id == MembershipRole.membership_id).where(
            MembershipRole.role_id == owner_role.id, TenantMembership.status == "active"))
        if owners <= 1:
            raise Conflict("An organization must keep at least one owner", code="last_owner")
    m.status = "removed"
    for emp in db.scalars(select(Employee).where(Employee.membership_id == m.id)):
        emp.membership_id = None
    db.execute(update(AuthSession).where(AuthSession.identity_id == m.identity_id,
                                         AuthSession.active_tenant_id == tenant_id,
                                         AuthSession.revoked_at.is_(None)).values(revoked_at=utcnow()))
    record_audit(db, tenant_id=tenant_id, actor=actor.id, action="member.removed", entity_type="membership",
                 entity_id=m.id, ip=ip)
    db.commit()


def list_audit_logs(db: Session, params, action: str | None = None):
    from app.core.pagination import paginate

    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    if action:
        stmt = stmt.where(AuditLog.action == action)
    return paginate(db, stmt, params)
