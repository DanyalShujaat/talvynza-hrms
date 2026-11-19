"""The Alembic migration chain must build exactly the schema the models declare."""
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from alembic import command
from app.db.base import Base


def _cfg(url, monkeypatch):
    monkeypatch.setenv("TALVYNZA_DATABASE_URL", url)
    from app.core.config import get_settings
    get_settings.cache_clear()
    return Config("alembic.ini")


def test_upgrade_head_matches_models_and_downgrades(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path/'m.db'}"
    cfg = _cfg(url, monkeypatch)
    command.upgrade(cfg, "head")
    eng = create_engine(url)
    tables = set(inspect(eng).get_table_names())
    assert {"identities", "sessions", "tenants", "tenant_memberships", "roles", "audit_logs"} <= tables
    with eng.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], f"models and migrations have drifted: {diff}"
    command.downgrade(cfg, "base")
    assert set(inspect(create_engine(url)).get_table_names()) <= {"alembic_version"}
    monkeypatch.undo()
    from app.core.config import get_settings
    get_settings.cache_clear()
