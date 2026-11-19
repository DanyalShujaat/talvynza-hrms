import pyotp
from sqlalchemy import select

from app.core import email as email_mod
from app.modules.identity.models import Identity, SecurityEvent
from tests.conftest import PASSWORD, last_token

REG = {"password": PASSWORD, "full_name": "Sam Tester", "organization_name": "Tester Co",
       "country": "PK", "currency": "PKR", "timezone": "Asia/Karachi"}


def test_register_login_and_me(signup):
    api = signup()
    me = api.get("/api/v1/me").json()
    assert me["identity"]["email"] == "owner@acme.test"
    assert me["active_organization"]["name"] == "Acme Ltd"
    assert me["active_organization"]["status"] == "trialing"
    assert me["roles"] == ["owner"]
    assert "payroll.approve" in me["permissions"]


def test_login_requires_verified_email(new_client):
    api = new_client()
    api.post("/api/v1/auth/register", {**REG, "email": "a@x.test"})
    r = api.post("/api/v1/auth/login", {"email": "a@x.test", "password": PASSWORD})
    assert r.status_code == 403 and r.json()["error"]["code"] == "email_not_verified"


def test_register_does_not_enumerate_accounts(new_client):
    api = new_client()
    r1 = api.post("/api/v1/auth/register", {**REG, "email": "dup@x.test"})
    r2 = api.post("/api/v1/auth/register", {**REG, "email": "dup@x.test"})
    assert r1.status_code == r2.status_code == 202 and r1.json() == r2.json()


def test_weak_password_rejected(new_client):
    api = new_client()
    r = api.post("/api/v1/auth/register", {**REG, "email": "w@x.test", "password": "short"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "weak_password"


def test_bad_org_inputs_rejected(new_client):
    api = new_client()
    r = api.post("/api/v1/auth/register", {**REG, "email": "z@x.test", "timezone": "Mars/Olympus"})
    assert r.status_code == 422


def test_wrong_password_and_lockout(signup, new_client):
    signup("lock@x.test")
    api = new_client()
    for _ in range(5):
        r = api.post("/api/v1/auth/login", {"email": "lock@x.test", "password": "Wrong-password-1!"})
        assert r.status_code == 401
    # Even the right password is refused while locked
    r = api.post("/api/v1/auth/login", {"email": "lock@x.test", "password": PASSWORD})
    assert r.status_code == 429 and r.json()["error"]["code"] == "account_locked"


def test_unknown_account_same_error_as_wrong_password(signup, new_client):
    signup("real@x.test")
    api = new_client()
    a = api.post("/api/v1/auth/login", {"email": "ghost@x.test", "password": PASSWORD})
    b = api.post("/api/v1/auth/login", {"email": "real@x.test", "password": "Wrong-password-1!"})
    assert a.status_code == b.status_code == 401
    assert a.json()["error"]["code"] == b.json()["error"]["code"]


def test_csrf_required_on_unsafe_requests(signup):
    api = signup()
    r = api.c.post("/api/v1/auth/logout")  # no CSRF header
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"
    r = api.c.post("/api/v1/auth/logout", headers={"X-CSRF-Token": "forged"})
    assert r.status_code == 403
    assert api.post("/api/v1/auth/logout").status_code == 204


def test_foreign_origin_blocked(signup):
    api = signup()
    r = api.post("/api/v1/auth/logout", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "bad_origin"


def test_logout_revokes_session_server_side(signup, new_client):
    api = signup()
    cookie = api.c.cookies.get("nx_session")
    api.post("/api/v1/auth/logout")
    replay = new_client()
    replay.c.cookies.set("nx_session", cookie)
    assert replay.get("/api/v1/me").status_code == 401


def test_session_cookie_is_httponly(new_client, signup):
    api = new_client()
    api.post("/api/v1/auth/register", {**REG, "email": "c@x.test"})
    api.post("/api/v1/auth/verify-email", {"token": last_token("verify-email")})
    r = api.post("/api/v1/auth/login", {"email": "c@x.test", "password": PASSWORD})
    set_cookie = [v for k, v in r.headers.multi_items() if k == "set-cookie"]
    session_cookie = next(c for c in set_cookie if c.startswith("nx_session="))
    csrf_cookie = next(c for c in set_cookie if c.startswith("nx_csrf="))
    assert "httponly" in session_cookie.lower() and "samesite=lax" in session_cookie.lower()
    assert "httponly" not in csrf_cookie.lower()


def test_password_reset_revokes_all_sessions(signup, new_client):
    api = signup("reset@x.test")
    new_client().post("/api/v1/auth/forgot-password", {"email": "reset@x.test"})
    token = last_token("reset-password")
    fresh = new_client()
    assert fresh.post("/api/v1/auth/reset-password", {"token": token, "new_password": "Brand-New-Passw0rd!"}).status_code == 200
    assert api.get("/api/v1/me").status_code == 401  # old session dead
    # token is single-use
    assert fresh.post("/api/v1/auth/reset-password", {"token": token, "new_password": "Another-Passw0rd!!"}).status_code == 422
    assert fresh.post("/api/v1/auth/login", {"email": "reset@x.test", "password": "Brand-New-Passw0rd!"}).status_code == 200


def test_forgot_password_unknown_email_is_silent(new_client):
    api = new_client()
    r = api.post("/api/v1/auth/forgot-password", {"email": "nobody@x.test"})
    assert r.status_code == 202 and not email_mod.OUTBOX


def test_mfa_flow_with_replay_protection_and_recovery(signup, new_client):
    api = signup("mfa@x.test")
    setup = api.post("/api/v1/auth/mfa/setup").json()
    totp = pyotp.TOTP(setup["secret"])
    r = api.post("/api/v1/auth/mfa/enable", {"code": totp.now()})
    assert r.status_code == 200
    recovery = r.json()["recovery_codes"]
    assert len(recovery) == 8

    other = new_client()
    r = other.post("/api/v1/auth/login", {"email": "mfa@x.test", "password": PASSWORD})
    assert r.status_code == 401 and r.json()["error"]["code"] == "mfa_required"
    # the code used during enable cannot be replayed to log in
    r = other.post("/api/v1/auth/login", {"email": "mfa@x.test", "password": PASSWORD, "mfa_code": totp.now()})
    assert r.status_code == 401
    # recovery code works exactly once
    ok = other.post("/api/v1/auth/login", {"email": "mfa@x.test", "password": PASSWORD, "mfa_code": recovery[0]})
    assert ok.status_code == 200
    again = new_client().post("/api/v1/auth/login", {"email": "mfa@x.test", "password": PASSWORD, "mfa_code": recovery[0]})
    assert again.status_code == 401


def test_mfa_secret_encrypted_at_rest(signup, db):
    api = signup("enc@x.test")
    secret = api.post("/api/v1/auth/mfa/setup").json()["secret"]
    raw = db.connection().exec_driver_sql("SELECT mfa_secret FROM identities").scalar()
    assert raw and secret not in raw


def test_failed_logins_recorded_as_security_events(signup, new_client, db):
    signup("evt@x.test")
    new_client().post("/api/v1/auth/login", {"email": "evt@x.test", "password": "Wrong-password-1!"})
    types = {e.event_type for e in db.scalars(select(SecurityEvent))}
    assert {"login_failed", "login_success"} <= types


def test_sessions_listing_and_remote_revocation(signup, new_client):
    a = signup("multi@x.test")
    b = new_client()
    b.post("/api/v1/auth/login", {"email": "multi@x.test", "password": PASSWORD})
    sessions = a.get("/api/v1/auth/sessions").json()
    assert len(sessions) == 2
    other = next(s for s in sessions if not s["current"])
    assert a.delete(f"/api/v1/auth/sessions/{other['id']}").status_code == 204
    assert b.get("/api/v1/me").status_code == 401
    assert a.get("/api/v1/me").status_code == 200


def test_error_envelope_shape(new_client):
    r = new_client().get("/api/v1/me")
    err = r.json()["error"]
    assert r.status_code == 401 and {"code", "message", "request_id"} <= set(err)
    assert r.headers["x-request-id"] == err["request_id"]


def test_identity_unverified_email_not_leaked_in_db_as_plain_password(signup, db):
    signup("hash@x.test")
    ident = db.scalar(select(Identity))
    assert ident.password_hash.startswith("$argon2") and PASSWORD not in ident.password_hash
