"""
Application settings for AnonyMus v3.

All values are read from environment variables (or .env file via pydantic-settings).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TEST = "test"


class Settings(BaseSettings):
    """Unified settings — replaces the ad-hoc os.getenv() calls scattered across the codebase."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ────────────────────────────────────────────────────────────
    environment: Environment = Field(default=Environment.DEVELOPMENT)
    debug: bool = Field(default=False)
    secret_key: str = Field(
        default="CHANGE_ME_IN_PRODUCTION", description="Flask/FastAPI session secret"
    )

    # ── Server ─────────────────────────────────────────────────────────────────
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=5000, ge=1, le=65535)
    workers: int = Field(default=1, ge=1)

    # ── Database ───────────────────────────────────────────────────────────────
    database_url: str = Field(
        default="sqlite+aiosqlite:///./anonymus.db",
        description="SQLAlchemy async DB URL (sqlite+aiosqlite:// or postgresql+asyncpg://)",
    )
    db_key: str = Field(
        default="",
        description="SQLCipher passphrase / DB encryption key (leave empty to disable encryption)",
    )

    # ── Tor ────────────────────────────────────────────────────────────────────
    tor_enabled: bool = Field(default=True)
    tor_control_port: int = Field(default=9051)
    tor_socks_port: int = Field(default=9050)

    # ── Rate Limiting ──────────────────────────────────────────────────────────
    rate_limit_default: str = Field(default="60/minute")
    rate_limit_auth: str = Field(default="10/minute")

    # ── Observability ──────────────────────────────────────────────────────────
    sentry_dsn: str = Field(default="", description="Sentry DSN (empty = disabled)")
    otel_endpoint: str = Field(
        default="", description="OpenTelemetry collector endpoint"
    )
    log_level: str = Field(default="INFO")

    # ── Feature Flags ──────────────────────────────────────────────────────────
    enable_v3_api: bool = Field(
        default=True,
        description="Mount the FastAPI v3 router alongside the legacy Flask app",
    )

    @field_validator("secret_key")
    @classmethod
    def _secret_key_not_default_in_prod(cls, v: str, info) -> str:
        # Validated at startup — prevents shipping with the placeholder key.
        if v == "CHANGE_ME_IN_PRODUCTION":
            import os

            if os.getenv("ENVIRONMENT", "development").lower() == "production":
                raise ValueError("SECRET_KEY must be set in production")
        return v

    @property
    def is_development(self) -> bool:
        return self.environment == Environment.DEVELOPMENT

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION

    @property
    def is_test(self) -> bool:
        return self.environment == Environment.TEST


# Module-level singleton — import anywhere as `from core.config import settings`
settings = Settings()
