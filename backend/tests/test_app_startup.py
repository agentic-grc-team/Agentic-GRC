"""The app validates its settings at startup, before /health can answer."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.main as main_module
from app.core.config import Settings


def test_app_refuses_to_start_with_an_insecure_remote_model_host(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "get_settings",
        lambda: Settings(_env_file=None, agrc_ollama_host="http://models.example.org"),
    )

    with pytest.raises(ValidationError, match="must use HTTPS"):
        with TestClient(main_module.app):
            pass


def test_app_starts_and_reports_health_with_valid_settings(monkeypatch):
    monkeypatch.setattr(main_module, "get_settings", lambda: Settings(_env_file=None))

    with TestClient(main_module.app) as client:
        assert client.get("/api/v1/health").json() == {"status": "ok"}
