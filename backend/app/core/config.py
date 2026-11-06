from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = Path(os.environ.get("AGRC_ENV_FILE", str(BACKEND_DIR / ".env")))
if not ENV_FILE.is_absolute():
    ENV_FILE = BACKEND_DIR / ENV_FILE


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
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
    interview_data_mode: Literal["synthetic", "approved_anonymized", "real"] = "synthetic"
    interview_anonymized_data_approved: bool = False
    interview_external_transfer_approved: bool = False
    interview_retention_approved: bool = False
    interview_deletion_approved: bool = False
    interview_redaction_approved: bool = False
    interview_storage_approved: bool = False
    interview_topology_documented: bool = False
    agrc_ollama_host: str = "http://127.0.0.1:11434"
    agrc_llm_model: str = "llama3.1:8b"
    agrc_llm_timeout_s: float = 8
    agrc_llm_retries: int = 1
    agrc_llm_keep_alive: str = "30m"
    agrc_llm_num_predict: int = Field(default=320, ge=32, le=2048)
    agrc_max_follow_ups: int = 3
    agrc_kb_path: Path | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_sender_email: str | None = None
    smtp_starttls: bool = True
    smtp_timeout_seconds: int = 10
    allow_demo_report: bool = False

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

    @field_validator("agrc_ollama_host")
    @classmethod
    def validate_interview_model_host(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        parsed = urlsplit(normalized)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "AGRC_OLLAMA_HOST must be an HTTP(S) URL without credentials, query, or fragment."
            )
        return normalized

    @model_validator(mode="after")
    def validate_deployment_security(self) -> Settings:
        model_host = urlsplit(self.agrc_ollama_host)
        is_local_model_host = model_host.hostname in {"localhost", "127.0.0.1", "::1"}
        if not is_local_model_host:
            if model_host.scheme != "https":
                raise ValueError("A remote interview model host must use HTTPS.")
            if not self.interview_external_transfer_approved:
                raise ValueError(
                    "A remote interview model requires INTERVIEW_EXTERNAL_TRANSFER_APPROVED=true."
                )
            if not self.interview_topology_documented:
                raise ValueError(
                    "A remote interview model requires INTERVIEW_TOPOLOGY_DOCUMENTED=true."
                )

        if bool(self.smtp_username) != (self.smtp_password is not None):
            raise ValueError("Set both SMTP_USERNAME and SMTP_PASSWORD, or leave both unset.")
        if (
            self.interview_data_mode == "approved_anonymized"
            and not self.interview_anonymized_data_approved
        ):
            raise ValueError(
                "Approved anonymized interview data requires "
                "INTERVIEW_ANONYMIZED_DATA_APPROVED=true."
            )
        if self.interview_data_mode == "real":
            required_interview_approvals = (
                ("INTERVIEW_EXTERNAL_TRANSFER_APPROVED", self.interview_external_transfer_approved),
                ("INTERVIEW_RETENTION_APPROVED", self.interview_retention_approved),
                ("INTERVIEW_DELETION_APPROVED", self.interview_deletion_approved),
                ("INTERVIEW_REDACTION_APPROVED", self.interview_redaction_approved),
                ("INTERVIEW_STORAGE_APPROVED", self.interview_storage_approved),
                ("INTERVIEW_TOPOLOGY_DOCUMENTED", self.interview_topology_documented),
            )
            missing_interview_approvals = [
                name for name, approved in required_interview_approvals if not approved
            ]
            if missing_interview_approvals:
                missing = ", ".join(missing_interview_approvals)
                raise ValueError(
                    "Real interview data is blocked until all data-policy gates are approved: "
                    + missing
                    + "."
                )
        if self.app_environment == "production":
            if self.allow_demo_report:
                raise ValueError("ALLOW_DEMO_REPORT must be false in production.")
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
