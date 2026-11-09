"""Rules for the interview model endpoint: local by default, remote only when secured and approved."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

REMOTE = "https://models.example.org"
TOKEN = "model-token-must-not-leak"
APPROVED = {
    "interview_external_transfer_approved": True,
    "interview_topology_documented": True,
}


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_local_model_host_needs_no_key_or_approvals():
    settings = _settings(agrc_ollama_host="http://127.0.0.1:11434")
    assert settings.ollama_api_key is None


def test_remote_model_host_with_https_key_and_approvals_is_accepted():
    settings = _settings(agrc_ollama_host=REMOTE + "/", agrc_ollama_api_key=TOKEN, **APPROVED)
    assert settings.agrc_ollama_host == REMOTE
    assert settings.ollama_api_key == TOKEN


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"agrc_ollama_host": "http://models.example.org", "agrc_ollama_api_key": TOKEN, **APPROVED},
            "must use HTTPS",
        ),
        (
            {
                "agrc_ollama_host": REMOTE,
                "agrc_ollama_api_key": TOKEN,
                "interview_topology_documented": True,
            },
            "INTERVIEW_EXTERNAL_TRANSFER_APPROVED",
        ),
        (
            {
                "agrc_ollama_host": REMOTE,
                "agrc_ollama_api_key": TOKEN,
                "interview_external_transfer_approved": True,
            },
            "INTERVIEW_TOPOLOGY_DOCUMENTED",
        ),
        ({"agrc_ollama_host": REMOTE, **APPROVED}, "AGRC_OLLAMA_API_KEY"),
        (
            {"agrc_ollama_host": "https://user:pass@models.example.org", **APPROVED},
            "without credentials",
        ),
    ],
)
def test_remote_model_host_is_rejected_unless_secured_and_approved(overrides, message):
    with pytest.raises(ValidationError, match=message):
        _settings(**overrides)


def test_model_api_key_is_not_exposed_in_repr_or_errors():
    settings = _settings(agrc_ollama_host=REMOTE, agrc_ollama_api_key=TOKEN, **APPROVED)
    assert TOKEN not in repr(settings)
    assert TOKEN not in str(settings.model_dump())

    with pytest.raises(ValidationError) as excinfo:
        _settings(agrc_ollama_host="http://models.example.org", agrc_ollama_api_key=TOKEN, **APPROVED)
    assert TOKEN not in str(excinfo.value)
