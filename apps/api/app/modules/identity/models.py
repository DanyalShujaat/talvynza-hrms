"""Identity: the login account (one per person, may belong to many tenants), sessions and tokens."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin
from app.db.types import EncryptedString, UTCDateTime


class Identity(Base, IdMixin, TimestampMixin):
    __tablename__ = "identities"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)  # stored lowercase
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_secret: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    mfa_last_step: Mapped[int | None] = mapped_column(Integer, nullable=True)  # TOTP replay protection
    mfa_recovery_hashes: Mapped[list] = mapped_column(JSON, default=list)


class AuthSession(Base, IdMixin):
    """Server-side browser session. Opaque token lives in an HTTP-only cookie; only its hash is stored."""

    __tablename__ = "sessions"
    __table_args__ = (Index("ix_sessions_identity_active", "identity_id", "revoked_at"),)

    identity_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("identities.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # Active tenant is chosen server-side; the frontend can request a switch but never assert a tenant.
    active_tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)


class EmailToken(Base, IdMixin):
    """Single-use tokens for email verification and password reset (hash stored, never the token)."""

    __tablename__ = "email_tokens"

    identity_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("identities.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(32))  # verify_email | reset_password
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class SecurityEvent(Base, IdMixin):
    """Platform-level security log (failed logins, lockouts, MFA changes). Not tenant-scoped."""

    __tablename__ = "security_events"

    identity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
