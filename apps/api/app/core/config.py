"""Application settings. Every value is overridable via TALVYNZA_* environment variables."""
from __future__ import annotations

import base64
import hashlib
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_DEFAULT_SECRET = "dev-only-insecure-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="TALVYNZA_", extra="ignore")

    environment: str = "development"  # development | test | production
    database_url: str = "sqlite:///./talvynza_dev.db"
    redis_url: str | None = None

    secret_key: str = INSECURE_DEFAULT_SECRET
    field_encryption_key: str | None = None  # urlsafe-base64 32 bytes; derived from secret_key in dev

    # Sessions & cookies
    session_cookie_name: str = "nx_session"
    csrf_cookie_name: str = "nx_csrf"
    session_absolute_hours: int = 12
    session_idle_minutes: int = 120
    cookie_secure: bool | None = None  # defaults to True in production
    cookie_samesite: str = "lax"

    # Account protection
    login_max_failures: int = 5
    lockout_minutes: int = 15
    require_email_verification: bool = True
    rate_limit_enabled: bool = True
    auth_rate_limit_per_minute: int = 20

    # Web
    cors_origins: str = "http://localhost:5173"
    frontend_url: str = "http://localhost:5173"

    # Email adapter: console | memory | smtp
    email_backend: str = "console"
    email_from: str = "no-reply@talvynza.local"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None

    storage_dir: str = "./storage"
    demo_accounts_file: str | None = None  # explicit local-only fictional demo accounts
    trial_days: int = 14
    log_json: bool = True

    # Tali uses a local Ollama model. Disabled until an operator opts in.
    ai_enabled: bool = False
    ai_provider: Literal["ollama", "groq"] = "ollama"
    ai_ollama_url: str = "http://127.0.0.1:11434"
    ai_model: str = "qwen3:0.6b"
    ai_groq_api_key: SecretStr | None = None
    ai_groq_model: str = "openai/gpt-oss-20b"

    @model_validator(mode="after")
    def _validate(self) -> Settings:
        if self.environment == "production":
            if self.secret_key == INSECURE_DEFAULT_SECRET or len(self.secret_key) < 32:
                raise ValueError("TALVYNZA_SECRET_KEY must be set to a strong value (>=32 chars) in production")
            if self.email_backend != "smtp" or not self.smtp_host:
                raise ValueError("Production requires the SMTP email backend and TALVYNZA_SMTP_HOST")
            if self.demo_accounts_file:
                raise ValueError("Demo account access is never allowed in production")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def secure_cookies(self) -> bool:
        return self.cookie_secure if self.cookie_secure is not None else self.environment == "production"

    @property
    def fernet_key(self) -> bytes:
        if self.field_encryption_key:
            return self.field_encryption_key.encode()
        return base64.urlsafe_b64encode(hashlib.sha256(("fld:" + self.secret_key).encode()).digest())


@lru_cache
def get_settings() -> Settings:
    return Settings()
