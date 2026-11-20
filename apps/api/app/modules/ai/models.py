"""One-time, tenant-scoped confirmations for actions suggested by Tali."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantScoped, utcnow
from app.db.types import UTCDateTime


class AssistantProposal(Base, IdMixin, TenantScoped):
    __tablename__ = "assistant_proposals"

    identity_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("identities.id"), index=True)
    action: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
