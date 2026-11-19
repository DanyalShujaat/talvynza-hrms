"""Declarative base and shared mixins."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, MetaData, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db.types import UTCDateTime

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class TenantScoped:
    """Marker mixin: rows belong to exactly one tenant.

    The ORM layer (app.db.tenant_scope) automatically appends `tenant_id = <session tenant>` to every
    SELECT/UPDATE/DELETE touching these entities and refuses to flush rows for another tenant.
    """

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="RESTRICT"), index=True, nullable=False
    )
