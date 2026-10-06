from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

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
    jwt_secret: SecretStr | None = None
    jwt_issuer: str = "agentic-grc"
    jwt_audience: str = "agentic-grc-api"
    jwt_access_token_minutes: int = 30
    app_base_url: str = "http://127.0.0.1:4178"
    app_environment: Literal["development", "test", "production"] = "development"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_sender_email: str | None = None
    smtp_starttls: bool = True
    smtp_timeout_seconds: int = 10

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(value.get_secret_value().encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET must contain at least 32 bytes.")
        return value

    @field_validator("jwt_access_token_minutes")
    @classmethod
    def validate_token_lifetime(cls, value: int) -> int:
        if not 1 <= value <= 1440:
            raise ValueError("JWT_ACCESS_TOKEN_MINUTES must be between 1 and 1440.")
        return value

    @model_validator(mode="after")
    def validate_deployment_security(self) -> Settings:
        if bool(self.smtp_username) != (self.smtp_password is not None):
            raise ValueError("Set both SMTP_USERNAME and SMTP_PASSWORD, or leave both unset.")
        if self.app_environment == "production":
            if self.jwt_secret is None:
                raise ValueError("JWT_SECRET must be configured in production.")
            if not self.app_base_url.startswith("https://"):
                raise ValueError("APP_BASE_URL must use HTTPS in production.")
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
