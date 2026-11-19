"""Portable column types (PostgreSQL in production, SQLite in local tests)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Text
from sqlalchemy.types import TypeDecorator

from app.core.security import decrypt_value, encrypt_value


class UTCDateTime(TypeDecorator):
    """Always stores UTC instants and always returns timezone-aware UTC datetimes."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetimes are not allowed; use timezone-aware UTC instants")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class EncryptedString(TypeDecorator):
    """Transparent Fernet encryption at rest for sensitive fields (salary, bank, national IDs, MFA)."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect):
        return None if value is None else encrypt_value(value)

    def process_result_value(self, value: str | None, dialect):
        return None if value is None else decrypt_value(value)
