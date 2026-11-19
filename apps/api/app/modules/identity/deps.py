"""FastAPI dependencies: authentication, CSRF, tenant context and permission checks."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import Forbidden, Unauthorized
from app.core.security import constant_time_equals, csrf_token_for, hash_token
from app.db.base import utcnow
from app.db.session import get_db
from app.db.tenant_scope import set_tenant
from app.modules.identity.models import AuthSession, Identity
from app.modules.tenancy import service as tenancy
from app.modules.tenancy.models import Tenant, TenantMembership

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass
class AuthContext:
    identity: Identity
    session: AuthSession
    ip: str | None
    tenant: Tenant | None = None
    membership: TenantMembership | None = None
    permissions: set[str] = field(default_factory=set)


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def check_origin(request: Request) -> None:
    """Reject cross-site unsafe requests whose Origin is not an allowed frontend origin."""
    if request.method in SAFE_METHODS:
        return
    origin = request.headers.get("origin")
    if origin and origin not in get_settings().cors_origin_list:
        raise Forbidden("Cross-origin request blocked", code="bad_origin")


def get_auth(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    s = get_settings()
    token = request.cookies.get(s.session_cookie_name)
    if not token:
        raise Unauthorized("Authentication required")
    sess = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    now = utcnow()
    if (sess is None or sess.revoked_at is not None or sess.expires_at <= now
            or sess.last_seen_at + timedelta(minutes=s.session_idle_minutes) <= now):
        raise Unauthorized("Session expired or revoked", code="session_expired")
    if request.method not in SAFE_METHODS:
        sent = request.headers.get("x-csrf-token", "")
        if not constant_time_equals(sent, csrf_token_for(token)):
            raise Forbidden("Missing or invalid CSRF token", code="csrf_failed")
    identity = db.get(Identity, sess.identity_id)
    if identity is None or not identity.is_active:
        raise Unauthorized("Account unavailable", code="session_expired")
    if now - sess.last_seen_at > timedelta(minutes=1):
        sess.last_seen_at = now
        db.commit()

    ctx = AuthContext(identity=identity, session=sess, ip=client_ip(request))
    if sess.active_tenant_id:
        membership = tenancy.get_active_membership(db, identity.id, sess.active_tenant_id)
        if membership is not None:
            if membership.tenant.status not in ("trialing", "active"):
                raise Forbidden("This organization is suspended or cancelled", code="tenant_suspended")
            # The ONLY place a tenant scope is established: derived from the server-side session + membership.
            set_tenant(db, membership.tenant_id)
            ctx.tenant, ctx.membership = membership.tenant, membership
            ctx.permissions = tenancy.permissions_for_membership(db, membership.id)
    return ctx


def get_tenant_ctx(ctx: AuthContext = Depends(get_auth)) -> AuthContext:
    if ctx.tenant is None:
        raise Forbidden("No active organization selected", code="no_active_tenant")
    return ctx


def require(*permissions: str):
    """Dependency factory enforcing that the caller holds ALL listed permissions in the active tenant."""

    def dep(ctx: AuthContext = Depends(get_tenant_ctx)) -> AuthContext:
        missing = [p for p in permissions if p not in ctx.permissions]
        if missing:
            raise Forbidden("You do not have permission to perform this action", code="permission_denied",
                            details=missing)
        return ctx

    return dep
