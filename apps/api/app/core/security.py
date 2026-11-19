"""Cryptographic and credential primitives."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

_ph = PasswordHasher()
# Verified against when the account does not exist so timing does not reveal account existence.
DUMMY_HASH = _ph.hash("talvynza-timing-equaliser")

_COMMON = {
    "password", "password1", "password123", "123456789012", "qwertyuiop12", "letmein12345",
    "administrator", "welcome12345", "iloveyou1234", "changeme1234",
}


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _ph.check_needs_rehash(password_hash)


def validate_password_strength(password: str, *, email: str | None = None, name: str | None = None) -> list[str]:
    """Returns a list of human-readable policy violations (empty == acceptable)."""
    problems: list[str] = []
    if len(password) < 12:
        problems.append("Password must be at least 12 characters long.")
    if len(password) > 128:
        problems.append("Password must be at most 128 characters long.")
    classes = sum(bool(re.search(p, password)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    if classes < 3:
        problems.append("Use at least three of: lowercase, uppercase, digits, symbols.")
    low = password.lower()
    if low in _COMMON:
        problems.append("Password is too common.")
    if email and email.split("@")[0].lower() in low and len(email.split("@")[0]) >= 4:
        problems.append("Password must not contain your email name.")
    if name and any(len(part) >= 4 and part.lower() in low for part in name.split()):
        problems.append("Password must not contain your name.")
    return problems


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """High-entropy random tokens only need a fast, unsalted hash to be safe at rest."""
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_token_for(session_token: str) -> str:
    """CSRF token bound to the session (HMAC), submitted by the SPA in X-CSRF-Token."""
    key = get_settings().secret_key.encode()
    return hmac.new(key, ("csrf:" + session_token).encode(), hashlib.sha256).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


# ---- field-level encryption (salary, bank details, government IDs, MFA secrets) ----
def _fernet() -> Fernet:
    return Fernet(get_settings().fernet_key)


def encrypt_value(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:  # pragma: no cover - indicates key rotation / tampering
        raise ValueError("Unable to decrypt field: wrong key or tampered data") from exc


# ---- TOTP MFA ----
def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="Talvynza HRMS")


def match_totp_step(secret: str, code: str, *, now: float | None = None) -> int | None:
    """Returns the matching 30s time-step (so callers can reject replays) or None."""
    code = code.strip().replace(" ", "")
    if not re.fullmatch(r"\d{6}", code):
        return None
    totp = pyotp.TOTP(secret)
    t = now if now is not None else time.time()
    for offset in (-1, 0, 1):
        step = int(t // 30) + offset
        if hmac.compare_digest(totp.at(step * 30), code):
            return step
    return None


def new_recovery_codes(n: int = 8) -> list[str]:
    return [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(n)]
