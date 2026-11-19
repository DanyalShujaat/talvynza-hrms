import os

# Must be set before the app package is imported.
os.environ.update({
    "TALVYNZA_ENVIRONMENT": "test",
    "TALVYNZA_DATABASE_URL": "sqlite://",
    "TALVYNZA_EMAIL_BACKEND": "memory",
    "TALVYNZA_LOG_JSON": "false",
    "TALVYNZA_RATE_LIMIT_ENABLED": "false",
    "TALVYNZA_SECRET_KEY": "test-secret-key-test-secret-key-0123456789",
})

import re

import email_validator

email_validator.TEST_ENVIRONMENT = True  # allow reserved *.test domains in fixtures

import pytest
from fastapi.testclient import TestClient

from app.core import email as email_mod
from app.core.ratelimit import get_limiter
from app.db import session as dbsession
from app.db.base import Base
from app.main import app

PASSWORD = "Correct-Horse-Battery-9"


class Api:
    """TestClient wrapper that behaves like the SPA: echoes the CSRF cookie in X-CSRF-Token."""

    def __init__(self, client: TestClient):
        self.c = client

    def _h(self, extra=None):
        h = {}
        tok = self.c.cookies.get("nx_csrf")
        if tok:
            h["X-CSRF-Token"] = tok
        h.update(extra or {})
        return h

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, json=None, **kw):
        return self.c.post(url, json=json, headers=self._h(kw.pop("headers", None)), **kw)

    def put(self, url, json=None, **kw):
        return self.c.put(url, json=json, headers=self._h(kw.pop("headers", None)), **kw)

    def patch(self, url, json=None, **kw):
        return self.c.patch(url, json=json, headers=self._h(kw.pop("headers", None)), **kw)

    def delete(self, url, **kw):
        return self.c.delete(url, headers=self._h(kw.pop("headers", None)), **kw)


@pytest.fixture(autouse=True)
def _fresh_db():
    Base.metadata.drop_all(dbsession.engine)
    Base.metadata.create_all(dbsession.engine)
    email_mod.OUTBOX.clear()
    get_limiter().reset() if hasattr(get_limiter(), "reset") else None
    yield


@pytest.fixture()
def db():
    from app.db.tenant_scope import set_tenant  # noqa: F401

    with dbsession.SessionLocal() as s:
        yield s


@pytest.fixture()
def new_client():
    clients = []

    def make() -> Api:
        tc = TestClient(app)
        tc.__enter__()  # run lifespan (permission catalogue sync)
        clients.append(tc)
        return Api(tc)

    yield make
    for tc in clients:
        tc.__exit__(None, None, None)


def last_token(purpose_hint: str) -> str:
    for mail in reversed(email_mod.OUTBOX):
        m = re.search(r"token=([\w\-]+)", mail.body)
        if m and purpose_hint in mail.body:
            return m.group(1)
    raise AssertionError(f"no email with {purpose_hint!r} found")


@pytest.fixture()
def signup(new_client):
    """signup(email, org) -> logged-in Api for a brand new tenant owner."""

    def _signup(email="owner@acme.test", org="Acme Ltd", name="Olivia Owner", password=PASSWORD) -> Api:
        api = new_client()
        r = api.post("/api/v1/auth/register", {
            "email": email, "password": password, "full_name": name, "organization_name": org,
            "country": "PK", "currency": "PKR", "timezone": "Asia/Karachi", "expected_employee_count": 40})
        assert r.status_code == 202, r.text
        api.post("/api/v1/auth/verify-email", {"token": last_token("verify-email")})
        r = api.post("/api/v1/auth/login", {"email": email, "password": password})
        assert r.status_code == 200, r.text
        return api

    return _signup
