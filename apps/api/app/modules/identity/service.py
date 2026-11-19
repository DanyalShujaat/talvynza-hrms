"""Authentication & session business logic."""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import events
from app.core.config import get_settings
from app.core.email import send_email
from app.core.errors import Conflict, Forbidden, NotFound, TooManyRequests, Unauthorized, ValidationFailed
from app.core.security import (
    DUMMY_HASH,
    hash_password,
    hash_token,
    match_totp_step,
    new_recovery_codes,
    new_token,
    new_totp_secret,
    password_needs_rehash,
    totp_uri,
    validate_password_strength,
    verify_password,
)
from app.db.base import utcnow
from app.db.tenant_scope import ALL_TENANTS, tenant_scope
from app.modules.identity.models import AuthSession, EmailToken, Identity, SecurityEvent
from app.modules.tenancy import service as tenancy
from app.modules.tenancy.models import Invitation, Tenant


def normalize_email(email: str) -> str:
    return email.strip().lower()


def security_event(db: Session, event_type: str, *, identity_id=None, ip=None, ua=None, details=None) -> None:
    db.add(SecurityEvent(identity_id=identity_id, event_type=event_type, ip=ip, user_agent=(ua or "")[:300] or None,
                         details=details or {}, created_at=utcnow()))


def _issue_email_token(db: Session, identity: Identity, purpose: str, ttl: timedelta) -> str:
    token = new_token()
    db.add(EmailToken(identity_id=identity.id, purpose=purpose, token_hash=hash_token(token),
                      expires_at=utcnow() + ttl, created_at=utcnow()))
    return token


def _consume_email_token(db: Session, token: str, purpose: str) -> Identity:
    row = db.scalar(select(EmailToken).where(EmailToken.token_hash == hash_token(token),
                                             EmailToken.purpose == purpose))
    if row is None or row.used_at is not None or row.expires_at < utcnow():
        raise ValidationFailed("This link is invalid or has expired", code="invalid_token")
    row.used_at = utcnow()
    identity = db.get(Identity, row.identity_id)
    if identity is None:
        raise ValidationFailed("This link is invalid or has expired", code="invalid_token")
    return identity


# ---------------------------------------------------------------- registration & verification
def register(
    db: Session, *, email: str, password: str, full_name: str, organization_name: str, country: str,
    currency: str, timezone: str, expected_employee_count: int | None = None, ip: str | None = None,
) -> None:
    """Creates the identity AND its first tenant (owner). The response is identical whether or not the
    email already exists, so the endpoint cannot be used to enumerate accounts."""
    email = normalize_email(email)
    problems = validate_password_strength(password, email=email, name=full_name)
    if problems:
        raise ValidationFailed("Password does not meet the policy", details=problems, code="weak_password")
    existing = db.scalar(select(Identity).where(Identity.email == email))
    if existing is not None:
        send_email(email, "Sign-up attempt on Talvynza HRMS",
                   "Someone tried to register with this email, but an account already exists. "
                   f"Sign in or reset your password: {get_settings().frontend_url}/login")
        return
    identity = Identity(email=email, password_hash=hash_password(password), full_name=full_name.strip(),
                        password_changed_at=utcnow())
    db.add(identity)
    db.flush()
    tenancy.create_tenant(db, identity, name=organization_name, country=country, currency=currency,
                          timezone=timezone, expected_employee_count=expected_employee_count, ip=ip)
    token = _issue_email_token(db, identity, "verify_email", timedelta(hours=24))
    security_event(db, "register", identity_id=identity.id, ip=ip)
    db.commit()
    send_email(email, "Verify your Talvynza HRMS email",
               f"Welcome, {identity.full_name}!\n\nVerify your email: "
               f"{get_settings().frontend_url}/verify-email?token={token}\n\nThe link expires in 24 hours.")
    events.publish("identity.registered", {"identity_id": identity.id})


def verify_email(db: Session, token: str) -> None:
    identity = _consume_email_token(db, token, "verify_email")
    identity.email_verified_at = identity.email_verified_at or utcnow()
    security_event(db, "email_verified", identity_id=identity.id)
    db.commit()


def resend_verification(db: Session, email: str) -> None:
    identity = db.scalar(select(Identity).where(Identity.email == normalize_email(email)))
    if identity and identity.email_verified_at is None and identity.is_active:
        token = _issue_email_token(db, identity, "verify_email", timedelta(hours=24))
        db.commit()
        send_email(identity.email, "Verify your Talvynza HRMS email",
                   f"Verify your email: {get_settings().frontend_url}/verify-email?token={token}")


# ---------------------------------------------------------------- login
def _fail_login(db: Session, identity: Identity, ip, ua) -> None:
    s = get_settings()
    identity.failed_login_count += 1
    details = {"failures": identity.failed_login_count}
    if identity.failed_login_count >= s.login_max_failures:
        identity.locked_until = utcnow() + timedelta(minutes=s.lockout_minutes)
        identity.failed_login_count = 0
        security_event(db, "account_locked", identity_id=identity.id, ip=ip, ua=ua)
    security_event(db, "login_failed", identity_id=identity.id, ip=ip, ua=ua, details=details)
    db.commit()


def login(
    db: Session, *, email: str, password: str, mfa_code: str | None, ip: str | None, user_agent: str | None,
) -> tuple[str, AuthSession, Identity]:
    s = get_settings()
    identity = db.scalar(select(Identity).where(Identity.email == normalize_email(email)))
    if identity is None:
        verify_password(DUMMY_HASH, password)  # equalise timing
        security_event(db, "login_unknown_account", ip=ip, ua=user_agent)
        db.commit()
        raise Unauthorized("Invalid email or password", code="invalid_credentials")
    if identity.locked_until and identity.locked_until > utcnow():
        raise TooManyRequests("Account temporarily locked after repeated failed sign-ins. Try again later.",
                              code="account_locked")
    if not verify_password(identity.password_hash, password):
        _fail_login(db, identity, ip, user_agent)
        raise Unauthorized("Invalid email or password", code="invalid_credentials")
    if not identity.is_active:
        raise Forbidden("This account has been deactivated", code="account_disabled")
    if s.require_email_verification and identity.email_verified_at is None:
        raise Forbidden("Please verify your email address before signing in", code="email_not_verified")

    if identity.mfa_enabled:
        if not mfa_code:
            raise Unauthorized("Multi-factor code required", code="mfa_required")
        if not _check_mfa(db, identity, mfa_code):
            _fail_login(db, identity, ip, user_agent)
            raise Unauthorized("Invalid multi-factor code", code="invalid_mfa_code")

    identity.failed_login_count, identity.locked_until, identity.last_login_at = 0, None, utcnow()
    if password_needs_rehash(identity.password_hash):
        identity.password_hash = hash_password(password)

    token, sess = start_session(db, identity, ip=ip, user_agent=user_agent)
    security_event(db, "login_success", identity_id=identity.id, ip=ip, ua=user_agent)
    db.commit()
    return token, sess, identity


def start_session(db: Session, identity: Identity, *, ip: str | None, user_agent: str | None,
                  tenant_id: uuid.UUID | None = None) -> tuple[str, AuthSession]:
    """Creates a server-side session. Without tenant_id the first active organization is selected."""
    if tenant_id is None:
        for m in tenancy.list_identity_memberships(db, identity.id):
            if m.tenant.status in ("trialing", "active"):
                tenant_id = m.tenant_id
                break
    token = new_token()
    now = utcnow()
    sess = AuthSession(identity_id=identity.id, token_hash=hash_token(token), active_tenant_id=tenant_id,
                       created_at=now, last_seen_at=now,
                       expires_at=now + timedelta(hours=get_settings().session_absolute_hours),
                       ip=ip, user_agent=(user_agent or "")[:300] or None)
    db.add(sess)
    return token, sess


def invitation_info(db: Session, token: str) -> dict:
    """What an invitation link is for. Only someone holding the emailed link can call this usefully."""
    with tenant_scope(db, ALL_TENANTS):
        inv = db.scalar(select(Invitation).where(Invitation.token_hash == hash_token(token)))
        if inv is None or inv.accepted_at is not None or inv.expires_at < utcnow():
            raise NotFound("This invitation is invalid or has expired")
        tenant = db.get(Tenant, inv.tenant_id)
        return {"email": inv.email, "organization": tenant.name if tenant else None,
                "has_account": db.scalar(select(Identity.id).where(Identity.email == inv.email)) is not None}


def join(db: Session, *, token: str, full_name: str, password: str, ip: str | None,
         user_agent: str | None) -> tuple[str, AuthSession, Identity]:
    """An invited person without an account sets their name and password and joins the organization directly.
    The emailed link proves control of the address, so the new account is created already verified."""
    info = invitation_info(db, token)
    if info["has_account"]:
        raise Conflict("An account already exists for this email. Sign in to accept the invitation.",
                       code="account_exists")
    problems = validate_password_strength(password, email=info["email"], name=full_name)
    if problems:
        raise ValidationFailed("Password does not meet the policy", details=problems, code="weak_password")
    identity = Identity(email=info["email"], password_hash=hash_password(password), full_name=full_name.strip(),
                        password_changed_at=utcnow(), email_verified_at=utcnow())
    db.add(identity)
    db.flush()
    tenant = tenancy.accept_invitation(db, identity, token, ip=ip)
    session_token, sess = start_session(db, identity, ip=ip, user_agent=user_agent, tenant_id=tenant.id)
    security_event(db, "joined_by_invitation", identity_id=identity.id, ip=ip, ua=user_agent)
    db.commit()
    return session_token, sess, identity


def _check_mfa(db: Session, identity: Identity, code: str) -> bool:
    step = match_totp_step(identity.mfa_secret or "", code)
    if step is not None:
        if identity.mfa_last_step is not None and step <= identity.mfa_last_step:
            return False  # replayed code
        identity.mfa_last_step = step
        return True
    h = hash_token(code.strip().lower())
    if h in (identity.mfa_recovery_hashes or []):
        identity.mfa_recovery_hashes = [x for x in identity.mfa_recovery_hashes if x != h]  # single use
        security_event(db, "mfa_recovery_code_used", identity_id=identity.id)
        return True
    return False


# ---------------------------------------------------------------- sessions
def revoke_session(db: Session, identity_id: uuid.UUID, session_id: uuid.UUID) -> None:
    sess = db.scalar(select(AuthSession).where(AuthSession.id == session_id, AuthSession.identity_id == identity_id))
    if sess is None:
        raise NotFound("Session not found")
    sess.revoked_at = sess.revoked_at or utcnow()
    db.commit()


def revoke_all_sessions(db: Session, identity_id: uuid.UUID, *, except_id: uuid.UUID | None = None) -> None:
    stmt = update(AuthSession).where(AuthSession.identity_id == identity_id, AuthSession.revoked_at.is_(None))
    if except_id:
        stmt = stmt.where(AuthSession.id != except_id)
    db.execute(stmt.values(revoked_at=utcnow()))
    db.commit()


def list_sessions(db: Session, identity_id: uuid.UUID) -> list[AuthSession]:
    return list(db.scalars(select(AuthSession).where(
        AuthSession.identity_id == identity_id, AuthSession.revoked_at.is_(None),
        AuthSession.expires_at > utcnow()).order_by(AuthSession.created_at.desc())))


def switch_tenant(db: Session, identity: Identity, sess: AuthSession, tenant_id: uuid.UUID, ip=None) -> None:
    m = tenancy.get_active_membership(db, identity.id, tenant_id)
    if m is None:
        # Same response for "no such tenant" and "not yours": do not disclose tenant existence.
        raise NotFound("Organization not found")
    if m.tenant.status not in ("trialing", "active"):
        raise Forbidden("This organization is not active", code="tenant_suspended")
    sess.active_tenant_id = tenant_id
    tenancy.record_audit(db, tenant_id=tenant_id, actor=identity.id, action="tenant.switched_in",
                         entity_type="tenant", entity_id=tenant_id, ip=ip)
    db.commit()


# ---------------------------------------------------------------- password management
def request_password_reset(db: Session, email: str) -> None:
    identity = db.scalar(select(Identity).where(Identity.email == normalize_email(email)))
    if identity and identity.is_active:
        token = _issue_email_token(db, identity, "reset_password", timedelta(hours=1))
        security_event(db, "password_reset_requested", identity_id=identity.id)
        db.commit()
        send_email(identity.email, "Reset your Talvynza HRMS password",
                   f"Reset link (valid 1 hour): {get_settings().frontend_url}/reset-password?token={token}")


def reset_password(db: Session, token: str, new_password: str) -> None:
    identity = _consume_email_token(db, token, "reset_password")
    problems = validate_password_strength(new_password, email=identity.email, name=identity.full_name)
    if problems:
        raise ValidationFailed("Password does not meet the policy", details=problems, code="weak_password")
    identity.password_hash = hash_password(new_password)
    identity.password_changed_at = utcnow()
    identity.failed_login_count, identity.locked_until = 0, None
    db.execute(update(AuthSession).where(AuthSession.identity_id == identity.id, AuthSession.revoked_at.is_(None))
               .values(revoked_at=utcnow()))
    security_event(db, "password_reset_completed", identity_id=identity.id)
    db.commit()


def change_password(db: Session, identity: Identity, current: str, new: str, keep_session: uuid.UUID) -> None:
    if not verify_password(identity.password_hash, current):
        raise Unauthorized("Current password is incorrect", code="invalid_credentials")
    problems = validate_password_strength(new, email=identity.email, name=identity.full_name)
    if problems:
        raise ValidationFailed("Password does not meet the policy", details=problems, code="weak_password")
    identity.password_hash = hash_password(new)
    identity.password_changed_at = utcnow()
    security_event(db, "password_changed", identity_id=identity.id)
    db.commit()
    revoke_all_sessions(db, identity.id, except_id=keep_session)


# ---------------------------------------------------------------- MFA
def mfa_begin_setup(db: Session, identity: Identity) -> dict:
    if identity.mfa_enabled:
        raise Conflict("MFA is already enabled", code="mfa_already_enabled")
    identity.mfa_secret = new_totp_secret()
    db.commit()
    return {"secret": identity.mfa_secret, "otpauth_uri": totp_uri(identity.mfa_secret, identity.email)}


def mfa_enable(db: Session, identity: Identity, code: str) -> list[str]:
    if identity.mfa_enabled or not identity.mfa_secret:
        raise Conflict("Start MFA setup first", code="mfa_not_pending")
    step = match_totp_step(identity.mfa_secret, code)
    if step is None:
        raise ValidationFailed("Invalid code", code="invalid_mfa_code")
    codes = new_recovery_codes()
    identity.mfa_enabled, identity.mfa_last_step = True, step
    identity.mfa_recovery_hashes = [hash_token(c) for c in codes]
    security_event(db, "mfa_enabled", identity_id=identity.id)
    db.commit()
    return codes  # shown once


def mfa_disable(db: Session, identity: Identity, password: str, code: str) -> None:
    if not identity.mfa_enabled:
        raise Conflict("MFA is not enabled", code="mfa_not_enabled")
    if not verify_password(identity.password_hash, password):
        raise Unauthorized("Password is incorrect", code="invalid_credentials")
    if not _check_mfa(db, identity, code):
        raise ValidationFailed("Invalid code", code="invalid_mfa_code")
    identity.mfa_enabled, identity.mfa_secret, identity.mfa_last_step = False, None, None
    identity.mfa_recovery_hashes = []
    security_event(db, "mfa_disabled", identity_id=identity.id)
    db.commit()
