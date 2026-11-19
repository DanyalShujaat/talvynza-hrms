"""Company assets and their assignment history."""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantScoped, TimestampMixin


class Asset(Base, IdMixin, TimestampMixin, TenantScoped):
    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("tenant_id", "serial_number", name="uq_asset_serial"),)

    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(60))
    serial_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    condition: Mapped[str] = mapped_column(String(20), default="good")  # new | good | fair | damaged
    status: Mapped[str] = mapped_column(String(20), default="available")  # available|assigned|maintenance|retired
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class AssetAssignment(Base, IdMixin, TimestampMixin, TenantScoped):
    """History rows are closed with returned_on and never deleted."""

    __tablename__ = "asset_assignments"

    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("assets.id"), index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("employees.id"), index=True)
    assigned_on: Mapped[date] = mapped_column(Date)
    returned_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    condition_out: Mapped[str] = mapped_column(String(20))
    condition_in: Mapped[str | None] = mapped_column(String(20), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
