"""Tenancy: tenants, memberships, roles & permissions, invitations, audit log."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, UniqueConstraint, Uuid, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TenantScoped, TimestampMixin
from app.db.types import UTCDateTime


class Tenant(Base, IdMixin, TimestampMixin):
    __tablename__ = "tenants"

    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    legal_name: Mapped[str | None] = mapped_column(String(250), nullable=True)
    country: Mapped[str] = mapped_column(String(2))
    currency: Mapped[str] = mapped_column(String(3))
    timezone: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="trialing")  # trialing|active|suspended|cancelled
    plan_code: Mapped[str] = mapped_column(String(40), default="trial")
    trial_ends_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    employee_capacity: Mapped[int] = mapped_column(Integer, default=25)
    expected_employee_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled_modules: Mapped[list] = mapped_column(JSON, default=list)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    onboarding_state: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by_identity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("identities.id"), nullable=True)


class TenantMembership(Base, IdMixin, TimestampMixin):
    """Links an identity to a tenant. Deliberately NOT auto-scoped: it is the root used to *discover*
    which tenants an identity may enter; services always filter it by identity_id or tenant_id."""

    __tablename__ = "tenant_memberships"
    __table_args__ = (UniqueConstraint("tenant_id", "identity_id", name="uq_membership_tenant_identity"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="RESTRICT"), index=True)
    identity_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("identities.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|suspended|removed
    joined_at: Mapped[datetime] = mapped_column(UTCDateTime)

    tenant: Mapped[Tenant] = relationship(lazy="joined")


class Permission(Base):
    """Global permission catalogue (code-defined, synced at startup)."""

    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(80), primary_key=True)
    module: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(String(255))
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)


class Role(Base, IdMixin, TimestampMixin, TenantScoped):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_roles_tenant_key"),)

    key: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)  # default roles: permissions locked for owner


class RolePermission(Base, IdMixin, TenantScoped):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_code", name="uq_role_permission"),)

    role_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("roles.id", ondelete="CASCADE"), index=True)
    permission_code: Mapped[str] = mapped_column(String(80), ForeignKey("permissions.code"))


class MembershipRole(Base, IdMixin, TenantScoped):
    __tablename__ = "membership_roles"
    __table_args__ = (UniqueConstraint("membership_id", "role_id", name="uq_membership_role"),)

    membership_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenant_memberships.id", ondelete="CASCADE"), index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("roles.id", ondelete="CASCADE"))


class Invitation(Base, IdMixin, TenantScoped):
    __tablename__ = "invitations"

    email: Mapped[str] = mapped_column(String(320), index=True)
    role_key: Mapped[str] = mapped_column(String(60))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    invited_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("identities.id"))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class AuditLog(Base, IdMixin, TenantScoped):
    """Append-only. UPDATE/DELETE through the ORM is refused (see listeners below)."""

    __tablename__ = "audit_logs"

    actor_identity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)


@event.listens_for(AuditLog, "before_update")
@event.listens_for(AuditLog, "before_delete")
def _audit_is_immutable(mapper, connection, target):
    raise PermissionError("audit_logs are append-only")
