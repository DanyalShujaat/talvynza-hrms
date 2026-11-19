"""Database-layer tenant isolation (defence in depth below the service layer).

Every SQLAlchemy Session carries `session.info["tenant_scope"]`:

* a UUID           -> reads/updates/deletes of TenantScoped rows are filtered to that tenant, and
                      new rows are stamped with it (a different tenant_id raises TenantViolation);
* ALL_TENANTS      -> explicit, audited system context (background jobs, invitation lookup);
* missing / None   -> FAIL CLOSED: tenant-scoped queries return nothing and inserts are refused.

The scope is only ever set from the server-side session, never from a client-supplied tenant id.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session, with_loader_criteria

from app.db.base import TenantScoped

ALL_TENANTS = "__all_tenants__"
_KEY = "tenant_scope"


class TenantViolation(Exception):
    """Raised when code tries to write across a tenant boundary."""


def set_tenant(db: Session, tenant_id: uuid.UUID | None) -> None:
    db.info[_KEY] = tenant_id


def current_scope(db: Session):
    return db.info.get(_KEY)


@contextmanager
def tenant_scope(db: Session, tenant_id: uuid.UUID | str | None) -> Iterator[None]:
    """Temporarily switch scope (pass ALL_TENANTS for an explicit system context)."""
    previous = db.info.get(_KEY)
    db.info[_KEY] = tenant_id
    try:
        yield
        # Flush while the scope is still active so rows created inside the block are validated
        # (and stamped) against THIS scope rather than whatever scope is active at the next flush.
        db.flush()
    finally:
        db.info[_KEY] = previous


@event.listens_for(Session, "do_orm_execute")
def _apply_tenant_filter(state) -> None:
    if not (state.is_select or state.is_update or state.is_delete):
        return
    scope = state.session.info.get(_KEY)
    if scope == ALL_TENANTS:
        return
    tid = scope if isinstance(scope, uuid.UUID) else None
    state.statement = state.statement.options(
        with_loader_criteria(
            TenantScoped,
            lambda cls: cls.tenant_id == tid,  # tid None => matches nothing (fail closed)
            include_aliases=True,
        )
    )


@event.listens_for(Session, "before_flush")
def _guard_writes(session: Session, flush_context, instances) -> None:
    scope = session.info.get(_KEY)
    for obj in list(session.new):
        if not isinstance(obj, TenantScoped):
            continue
        if scope == ALL_TENANTS:
            if obj.tenant_id is None:
                raise TenantViolation(f"{type(obj).__name__} requires an explicit tenant_id in system scope")
        elif not isinstance(scope, uuid.UUID):
            raise TenantViolation(f"No tenant scope set; refusing to insert {type(obj).__name__}")
        elif obj.tenant_id is None:
            obj.tenant_id = scope
        elif obj.tenant_id != scope:
            raise TenantViolation(f"Cross-tenant insert refused for {type(obj).__name__}")
    for obj in list(session.dirty):
        if isinstance(obj, TenantScoped) and inspect(obj).attrs.tenant_id.history.has_changes():
            hist = inspect(obj).attrs.tenant_id.history
            if hist.deleted:  # tenant_id actually changed from an existing value
                raise TenantViolation(f"tenant_id is immutable on {type(obj).__name__}")
