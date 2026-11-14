import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.main as main_module
from app.core.config import Settings

FRONTEND_ORIGIN = "https://agentic-grc.pages.dev"


def _client_with(monkeypatch, **settings_kwargs) -> TestClient:
    settings = Settings(_env_file=None, **settings_kwargs)
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    return TestClient(main_module.create_app())


def test_preflight_from_allowed_origin_is_accepted(monkeypatch):
    client = _client_with(monkeypatch, cors_allowed_origins=f"{FRONTEND_ORIGIN}/")

    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": FRONTEND_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONTEND_ORIGIN
    assert "access-control-allow-credentials" not in response.headers


def test_simple_request_exposes_content_disposition(monkeypatch):
    client = _client_with(monkeypatch, cors_allowed_origins=FRONTEND_ORIGIN)

    response = client.get("/api/v1/health", headers={"Origin": FRONTEND_ORIGIN})

    assert response.headers["access-control-allow-origin"] == FRONTEND_ORIGIN
    assert "content-disposition" in response.headers["access-control-expose-headers"].lower()


def test_unlisted_origin_gets_no_cors_headers(monkeypatch):
    client = _client_with(monkeypatch, cors_allowed_origins=FRONTEND_ORIGIN)

    response = client.get("/api/v1/health", headers={"Origin": "https://evil.example"})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_cors_is_disabled_without_configured_origins(monkeypatch):
    client = _client_with(monkeypatch)

    response = client.get("/api/v1/health", headers={"Origin": FRONTEND_ORIGIN})

    assert "access-control-allow-origin" not in response.headers


def test_cors_origins_are_normalized():
    settings = Settings(
        _env_file=None,
        cors_allowed_origins=" https://a.pages.dev/ , ,http://localhost:4178",
    )

    assert settings.cors_origins == ["https://a.pages.dev", "http://localhost:4178"]


@pytest.mark.parametrize(
    "origin",
    ["*", "https://a.pages.dev/app", "ftp://a.pages.dev", "https://user:pw@a.pages.dev"],
)
def test_invalid_cors_origins_are_rejected(origin):
    with pytest.raises(ValidationError, match="CORS_ALLOWED_ORIGINS"):
        Settings(_env_file=None, cors_allowed_origins=origin)


def test_production_rejects_http_cors_origin():
    with pytest.raises(ValidationError, match="HTTPS in production"):
        Settings(
            _env_file=None,
            app_environment="production",
            app_base_url="https://agentic-grc.pages.dev",
            supabase_url="https://example.supabase.co",
            supabase_publishable_key="sb_publishable_x",
            supabase_secret_key="sb_secret_x",
            smtp_host="smtp.example.com",
            smtp_sender_email="noreply@example.com",
            cors_allowed_origins="http://agentic-grc.pages.dev",
        )
