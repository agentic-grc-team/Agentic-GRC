from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
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
    auth_issuer: str | None = None
    auth_audience: str | None = None
    auth_jwks_url: str | None = None

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
