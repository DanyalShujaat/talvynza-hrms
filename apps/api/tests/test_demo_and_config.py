import json

import pytest

from app.core.config import Settings, get_settings
from tests.conftest import PASSWORD


def test_demo_is_disabled_by_default_and_in_test_environment(new_client, tmp_path, monkeypatch):
    client = new_client()
    assert client.get("/api/v1/demo/accounts").status_code == 404
    assert client.post("/api/v1/demo/login", {"account": "admin"}).status_code == 404
    path = tmp_path / "accounts.json"
    path.write_text('{"accounts": []}')
    monkeypatch.setattr(get_settings(), "demo_accounts_file", str(path))
    assert client.get("/api/v1/demo/accounts").status_code == 404


def test_demo_uses_real_login_and_never_returns_passwords(signup, new_client, tmp_path, monkeypatch):
    signup()
    path = tmp_path / "accounts.json"
    path.write_text(json.dumps({"accounts": [{"key": "admin", "name": "Olivia Owner", "label": "Administrator",
                                              "email": "owner@acme.test", "password": PASSWORD}]}))
    monkeypatch.setattr(get_settings(), "environment", "development")
    monkeypatch.setattr(get_settings(), "demo_accounts_file", str(path))
    client = new_client()
    response = client.get("/api/v1/demo/accounts")
    assert response.status_code == 200 and PASSWORD not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert client.post("/api/v1/demo/login", {"account": "unknown"}).status_code == 404
    assert client.post("/api/v1/demo/login", {"account": "admin"}).status_code == 200
    assert client.get("/api/v1/me").json()["roles"] == ["owner"]


def test_production_rejects_console_email_and_demo_access():
    safe = {"environment": "production", "secret_key": "a-long-test-secret-that-is-at-least-32-characters",
            "email_backend": "smtp", "smtp_host": "mail.example.com"}
    with pytest.raises(ValueError, match="SMTP"):
        Settings(**{**safe, "email_backend": "console"})
    with pytest.raises(ValueError, match="Demo"):
        Settings(**safe, demo_accounts_file="demo.json")
    assert Settings(**safe).secure_cookies
