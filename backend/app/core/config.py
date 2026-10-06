from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    db_host: str | None = None
    db_port: int = 5432
    db_name: str = "agentic_grc"
    db_user: str | None = None
    db_password: SecretStr | None = None
    db_sslmode: Literal[
        "disable", "allow", "prefer", "require", "verify-ca", "verify-full"
    ] = "prefer"
    supabase_url: str | None = None
    supabase_publishable_key: SecretStr | None = None
    supabase_secret_key: SecretStr | None = None
    app_base_url: str = "http://127.0.0.1:4178"
    app_environment: Literal["development", "test", "production"] = "development"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_sender_email: str | None = None
    smtp_starttls: bool = True
    smtp_timeout_seconds: int = 10

    @field_validator("supabase_url")
    @classmethod
    def normalize_supabase_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().rstrip("/")
        parsed = urlsplit(normalized)
        is_local_http = parsed.scheme == "http" and parsed.hostname in {
            "localhost",
            "127.0.0.1",
            "::1",
        }
        if parsed.scheme != "https" and not is_local_http:
            raise ValueError("SUPABASE_URL must be an HTTPS URL (or a local development URL).")
        if not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("SUPABASE_URL must be a valid project URL without credentials.")
        return normalized

    @model_validator(mode="after")
    def validate_deployment_security(self) -> Settings:
        if bool(self.smtp_username) != (self.smtp_password is not None):
            raise ValueError("Set both SMTP_USERNAME and SMTP_PASSWORD, or leave both unset.")
        if self.app_environment == "production":
            if not self.app_base_url.startswith("https://"):
                raise ValueError("APP_BASE_URL must use HTTPS in production.")
            if not self.supabase_url or not self.supabase_url.startswith("https://"):
                raise ValueError("SUPABASE_URL must use HTTPS in production.")
            if self.supabase_publishable_key is None or self.supabase_secret_key is None:
                raise ValueError("Configure both Supabase API keys in production.")
            if not self.smtp_host or not self.smtp_sender_email:
                raise ValueError("Configure SMTP_HOST and SMTP_SENDER_EMAIL in production.")
            if not self.smtp_starttls:
                raise ValueError("SMTP_STARTTLS must be enabled in production.")
        return self

    @property
    def sqlalchemy_url(self) -> URL:
        missing = [
            field_name
            for field_name, value in (
                ("DB_HOST", self.db_host),
                ("DB_USER", self.db_user),
            )
            if not value
        ]
        if missing:
            names = ", ".join(missing)
            raise ValueError(f"Missing required PostgreSQL setting(s): {names}")

        password = (
            self.db_password.get_secret_value() if self.db_password is not None else None
        )
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.db_user,
            password=password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
            query={"sslmode": self.db_sslmode},
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
