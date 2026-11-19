"""Notification helpers shared by every module."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.email import send_email
from app.db.base import utcnow
from app.modules.employees.models import Employee
from app.modules.notifications.models import Notification
from app.modules.tenancy.models import MembershipRole, RolePermission, TenantMembership


def notify_membership(db: Session, tenant_id: uuid.UUID, membership_id: uuid.UUID | None, kind: str, title: str,
                      body: str | None = None, link: str | None = None, dedupe_key: str | None = None,
                      email: str | None = None) -> None:
    """Adds an in-app notification (deduplicated by key). Callers commit. Optionally sends an email."""
    if membership_id is None:
        return
    if dedupe_key and db.scalar(select(func.count()).select_from(Notification).where(
            Notification.membership_id == membership_id, Notification.dedupe_key == dedupe_key)):
        return
    db.add(Notification(tenant_id=tenant_id, membership_id=membership_id, kind=kind, title=title, body=body,
                        link=link, dedupe_key=dedupe_key, created_at=utcnow()))
    if email:
        send_email(email, title, body or title)


def notify_employee(db: Session, emp: Employee | None, kind: str, title: str, body: str | None = None,
                    link: str | None = None, dedupe_key: str | None = None) -> None:
    if emp is None or emp.membership_id is None:
        return
    notify_membership(db, emp.tenant_id, emp.membership_id, kind, title, body, link, dedupe_key)


def notify_permission_holders(db: Session, tenant_id: uuid.UUID, permission: str, kind: str, title: str,
                              body: str | None = None, link: str | None = None, dedupe_key: str | None = None,
                              exclude_identity_id: uuid.UUID | None = None) -> None:
    """Notify active members who can handle a cross-team queue item."""
    stmt = (select(TenantMembership).join(MembershipRole, MembershipRole.membership_id == TenantMembership.id)
            .join(RolePermission, RolePermission.role_id == MembershipRole.role_id)
            .where(TenantMembership.tenant_id == tenant_id, TenantMembership.status == "active",
                   RolePermission.permission_code == permission).distinct())
    for member in db.scalars(stmt):
        if member.identity_id != exclude_identity_id:
            notify_membership(db, tenant_id, member.id, kind, title, body, link, dedupe_key)
