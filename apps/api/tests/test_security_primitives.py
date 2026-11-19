import pytest

from app.core import security
from app.core.ratelimit import MemoryRateLimiter
from app.modules.tenancy.permissions import CATALOG, DEFAULT_ROLES


def test_password_policy():
    assert security.validate_password_strength("Correct-Horse-Battery-9") == []
    assert security.validate_password_strength("short1A!")  # too short
    assert security.validate_password_strength("alllowercaseletters")  # one class
    assert security.validate_password_strength("Danyal-Shujaat-1234", name="Danyal Shujaat")  # contains name
    assert security.validate_password_strength("johnsmith-Passw0rd!", email="johnsmith@x.com")


def test_hash_verify_roundtrip():
    h = security.hash_password("Correct-Horse-Battery-9")
    assert security.verify_password(h, "Correct-Horse-Battery-9")
    assert not security.verify_password(h, "wrong")
    assert not security.verify_password("not-a-hash", "x")


def test_field_encryption_roundtrip_and_tamper_detection():
    c = security.encrypt_value("PK36SCBL0000001123456702")
    assert "PK36" not in c and security.decrypt_value(c) == "PK36SCBL0000001123456702"
    with pytest.raises(ValueError):
        security.decrypt_value(c[:-4] + "AAAA")


def test_totp_replay_step_detection():
    secret = security.new_totp_secret()
    import pyotp
    code = pyotp.TOTP(secret).now()
    step = security.match_totp_step(secret, code)
    assert step is not None
    assert security.match_totp_step(secret, "000000") in (None, step)  # extremely unlikely collision
    assert security.match_totp_step(secret, "abc") is None


def test_csrf_token_bound_to_session():
    assert security.csrf_token_for("s1") != security.csrf_token_for("s2")
    assert security.csrf_token_for("s1") == security.csrf_token_for("s1")


def test_rate_limiter_blocks_after_limit():
    rl = MemoryRateLimiter()
    assert [rl.allow("k", 3, 60) for _ in range(5)] == [True, True, True, False, False]
    assert rl.allow("other", 3, 60)


def test_default_roles_reference_only_known_permissions_and_separate_payroll_duties():
    for key, (_, _, perms) in DEFAULT_ROLES.items():
        assert perms <= set(CATALOG), key
    # Segregation of duties: no non-owner default role can both process and approve payroll
    for key, (_, _, perms) in DEFAULT_ROLES.items():
        if key != "owner":
            assert not {"payroll.process", "payroll.approve"} <= perms, key
    assert "salary.read" not in DEFAULT_ROLES["employee"][2]
    assert "salary.read" not in DEFAULT_ROLES["reporting_manager"][2]
