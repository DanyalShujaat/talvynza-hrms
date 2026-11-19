from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.ratelimit import rate_limit
from app.core.security import csrf_token_for
from app.db.session import get_db
from app.modules.identity import service
from app.modules.identity.deps import AuthContext, check_origin, client_ip, get_auth
from app.modules.tenancy import service as tenancy

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(check_origin)])
me_router = APIRouter(tags=["auth"], dependencies=[Depends(check_origin)])
limited = Depends(rate_limit("auth"))


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    full_name: str = Field(min_length=2, max_length=200)
    organization_name: str = Field(min_length=2, max_length=200)
    country: str = Field(min_length=2, max_length=2, examples=["PK"])
    currency: str = Field(min_length=3, max_length=3, examples=["PKR"])
    timezone: str = Field(examples=["Asia/Karachi"])
    expected_employee_count: int | None = Field(default=None, ge=1, le=1_000_000)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)
    mfa_code: str | None = Field(default=None, max_length=32)


class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class EmailIn(BaseModel):
    email: EmailStr


class ResetIn(TokenIn):
    new_password: str = Field(max_length=256)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class CodeIn(BaseModel):
    code: str = Field(max_length=32)


class MfaDisableIn(CodeIn):
    password: str = Field(max_length=256)


class SwitchTenantIn(BaseModel):
    tenant_id: uuid.UUID


def _set_cookies(response: Response, token: str) -> None:
    s = get_settings()
    max_age = s.session_absolute_hours * 3600
    common = dict(max_age=max_age, secure=s.secure_cookies, samesite=s.cookie_samesite, path="/")
    response.set_cookie(s.session_cookie_name, token, httponly=True, **common)
    # Readable by the SPA, which echoes it in X-CSRF-Token (HMAC-bound to the session token).
    response.set_cookie(s.csrf_cookie_name, csrf_token_for(token), httponly=False, **common)


def _clear_cookies(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(s.session_cookie_name, path="/")
    response.delete_cookie(s.csrf_cookie_name, path="/")


@router.post("/register", status_code=202, dependencies=[limited])
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    service.register(db, email=body.email, password=body.password, full_name=body.full_name,
                     organization_name=body.organization_name, country=body.country, currency=body.currency,
                     timezone=body.timezone, expected_employee_count=body.expected_employee_count,
                     ip=client_ip(request))
    return {"message": "If the details are valid, a verification email has been sent."}


@router.post("/verify-email", dependencies=[limited])
def verify_email(body: TokenIn, db: Session = Depends(get_db)):
    service.verify_email(db, body.token)
    return {"message": "Email verified"}


@router.post("/resend-verification", status_code=202, dependencies=[limited])
def resend_verification(body: EmailIn, db: Session = Depends(get_db)):
    service.resend_verification(db, body.email)
    return {"message": "If the account exists and is unverified, a new email has been sent."}


@router.post("/login", dependencies=[limited])
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    token, sess, identity = service.login(
        db, email=body.email, password=body.password, mfa_code=body.mfa_code, ip=client_ip(request),
        user_agent=request.headers.get("user-agent"))
    _set_cookies(response, token)
    return {"identity": {"id": identity.id, "email": identity.email, "full_name": identity.full_name},
            "active_tenant_id": sess.active_tenant_id}


class JoinIn(TokenIn):
    full_name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=1, max_length=256)


@router.get("/invitation", dependencies=[limited])
def invitation(token: str, db: Session = Depends(get_db)):
    return service.invitation_info(db, token)


@router.post("/join", dependencies=[limited])
def join(body: JoinIn, request: Request, response: Response, db: Session = Depends(get_db)):
    token, sess, identity = service.join(db, token=body.token, full_name=body.full_name, password=body.password,
                                         ip=client_ip(request), user_agent=request.headers.get("user-agent"))
    _set_cookies(response, token)
    return {"identity": {"id": identity.id, "email": identity.email, "full_name": identity.full_name},
            "active_tenant_id": sess.active_tenant_id}


@router.post("/logout", status_code=204)
def logout(response: Response, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    service.revoke_session(db, ctx.identity.id, ctx.session.id)
    _clear_cookies(response)


@router.post("/logout-all", status_code=204)
def logout_all(response: Response, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    service.revoke_all_sessions(db, ctx.identity.id)
    _clear_cookies(response)


@router.post("/forgot-password", status_code=202, dependencies=[limited])
def forgot_password(body: EmailIn, db: Session = Depends(get_db)):
    service.request_password_reset(db, body.email)
    return {"message": "If the account exists, a reset link has been sent."}


@router.post("/reset-password", dependencies=[limited])
def reset_password(body: ResetIn, db: Session = Depends(get_db)):
    service.reset_password(db, body.token, body.new_password)
    return {"message": "Password updated. Please sign in again."}


@router.post("/change-password", status_code=204)
def change_password(body: ChangePasswordIn, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    service.change_password(db, ctx.identity, body.current_password, body.new_password, ctx.session.id)


@router.get("/sessions")
def sessions(ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    return [{"id": s.id, "created_at": s.created_at, "last_seen_at": s.last_seen_at, "ip": s.ip,
             "user_agent": s.user_agent, "current": s.id == ctx.session.id}
            for s in service.list_sessions(db, ctx.identity.id)]


@router.delete("/sessions/{session_id}", status_code=204)
def revoke(session_id: uuid.UUID, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    service.revoke_session(db, ctx.identity.id, session_id)


@router.post("/mfa/setup")
def mfa_setup(ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    return service.mfa_begin_setup(db, ctx.identity)


@router.post("/mfa/enable")
def mfa_enable(body: CodeIn, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    return {"recovery_codes": service.mfa_enable(db, ctx.identity, body.code)}


@router.post("/mfa/disable", status_code=204)
def mfa_disable(body: MfaDisableIn, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    service.mfa_disable(db, ctx.identity, body.password, body.code)


def _employee_summary(db: Session, ctx: AuthContext) -> dict | None:
    from app.modules.employees import service as employees
    from app.modules.employees.models import Employee

    emp = employees.current_employee(db, ctx.membership.id) if ctx.membership else None
    if emp is None:
        return None
    names = employees.name_maps(db)
    reports = db.scalar(select(func.count()).select_from(Employee).where(
        Employee.manager_id == emp.id, Employee.deleted_at.is_(None))) or 0
    return {"id": emp.id, "employee_code": emp.employee_code, "full_name": emp.full_name,
            "designation": names["designation"].get(emp.designation_id),
            "department": names["department"].get(emp.department_id), "direct_reports": reports}


@me_router.get("/me")
def me(ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    memberships = [{"tenant_id": m.tenant_id, "name": m.tenant.name, "slug": m.tenant.slug,
                    "status": m.tenant.status} for m in tenancy.list_identity_memberships(db, ctx.identity.id)]
    roles = tenancy.role_keys_for_membership(db, ctx.membership.id) if ctx.membership else []
    t = ctx.tenant
    return {
        "identity": {"id": ctx.identity.id, "email": ctx.identity.email, "full_name": ctx.identity.full_name,
                     "mfa_enabled": ctx.identity.mfa_enabled, "is_platform_admin": ctx.identity.is_platform_admin,
                     "email_verified": ctx.identity.email_verified_at is not None},
        "organizations": memberships,
        "active_organization": None if t is None else {
            "id": t.id, "name": t.name, "slug": t.slug, "country": t.country, "currency": t.currency,
            "timezone": t.timezone, "status": t.status, "plan_code": t.plan_code,
            "trial_ends_at": t.trial_ends_at, "enabled_modules": t.enabled_modules},
        "roles": roles,
        "permissions": sorted(ctx.permissions),
        "employee": _employee_summary(db, ctx),
    }


@me_router.post("/me/switch-organization")
def switch_org(body: SwitchTenantIn, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    service.switch_tenant(db, ctx.identity, ctx.session, body.tenant_id, ip=ctx.ip)
    return {"active_tenant_id": body.tenant_id}
