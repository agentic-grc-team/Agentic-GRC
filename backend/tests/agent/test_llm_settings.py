import importlib
import pytest
from pydantic import BaseModel

import app.agent.config as config_module
from app.agent.llm import FakeLLM, OllamaLLM


class _DummyResponse(BaseModel):
    answer: str


def test_settings_defaults_and_env(monkeypatch):
    # Test defaults
    monkeypatch.delenv("AGRC_LLM_KEEP_ALIVE", raising=False)
    monkeypatch.delenv("AGRC_LLM_NUM_PREDICT", raising=False)
    importlib.reload(config_module)
    default_settings = config_module.Settings()
    assert default_settings.llm_keep_alive == "30m"
    assert default_settings.llm_num_predict == 320

    # Test reading from env
    monkeypatch.setenv("AGRC_LLM_KEEP_ALIVE", "15m")
    monkeypatch.setenv("AGRC_LLM_NUM_PREDICT", "500")
    importlib.reload(config_module)
    custom_settings = config_module.Settings()
    assert custom_settings.llm_keep_alive == "15m"
    assert custom_settings.llm_num_predict == 500

    # Clean up environment reload
    monkeypatch.delenv("AGRC_LLM_KEEP_ALIVE", raising=False)
    monkeypatch.delenv("AGRC_LLM_NUM_PREDICT", raising=False)
    importlib.reload(config_module)


def test_ollama_llm_structured_options_and_keep_alive(monkeypatch):
    pytest.importorskip("ollama")
    import ollama

    recorded_calls = []

    class FakeClient:
        def __init__(self, host=None, timeout=None):
            pass

        def chat(self, **kwargs):
            recorded_calls.append(kwargs)
            return {"message": {"content": '{"answer": "ok"}'}}

    monkeypatch.setattr(ollama, "Client", FakeClient)

    client = OllamaLLM(
        model_name="test-model",
        host="http://localhost:11434",
        timeout_s=5.0,
        keep_alive="45m",
        num_predict=256,
    )
    res, meta = client.structured(
        prompt_id="test_id",
        prompt_version="0.1.0",
        system="sys_prompt",
        user="user_prompt",
        schema=_DummyResponse,
    )

    assert res.answer == "ok"
    assert len(recorded_calls) == 1
    call = recorded_calls[0]
    assert call["keep_alive"] == "45m"
    assert call["options"]["temperature"] == 0
    assert call["options"]["num_predict"] == 256


def test_ollama_llm_warm_up_success_and_failure(monkeypatch):
    pytest.importorskip("ollama")
    import ollama

    # Success case
    class FakeClientSuccess:
        def __init__(self, host=None, timeout=None):
            self.generate_kwargs = None

        def generate(self, **kwargs):
            self.generate_kwargs = kwargs
            return {}

    fake_success = FakeClientSuccess()
    monkeypatch.setattr(ollama, "Client", lambda **kwargs: fake_success)

    llm = OllamaLLM("test-model", "http://localhost:11434", timeout_s=5.0, keep_alive="20m")
    load_time = llm.warm_up()
    assert isinstance(load_time, int)
    assert load_time >= 0
    assert fake_success.generate_kwargs is not None
    assert fake_success.generate_kwargs["model"] == "test-model"
    assert fake_success.generate_kwargs["prompt"] == ""
    assert fake_success.generate_kwargs["keep_alive"] == "20m"

    # Failure case: ConnectionError raised by generate
    class FakeClientFailure:
        def __init__(self, host=None, timeout=None):
            pass

        def generate(self, **kwargs):
            raise ConnectionError("Ollama daemon is down")

    monkeypatch.setattr(ollama, "Client", lambda **kwargs: FakeClientFailure())
    llm_fail = OllamaLLM("test-model", "http://localhost:11434", timeout_s=5.0)
    failed_result = llm_fail.warm_up()
    assert failed_result is None


def test_fake_llm_warm_up():
    fake = FakeLLM({})
    assert fake.warm_up() == 0


@pytest.mark.parametrize(
    ("api_key", "expected_headers"),
    [(None, None), ("model-token", {"Authorization": "Bearer model-token"})],
)
def test_ollama_llm_sends_bearer_token_only_when_configured(monkeypatch, api_key, expected_headers):
    pytest.importorskip("ollama")
    import ollama

    recorded = {}

    class FakeClient:
        def __init__(self, host=None, timeout=None, **kwargs):
            recorded.update(kwargs)

    monkeypatch.setattr(ollama, "Client", FakeClient)

    OllamaLLM(model_name="m", host="https://models.example.org", timeout_s=5.0, api_key=api_key)

    assert recorded.get("headers") == expected_headers


def test_agent_settings_keep_api_key_out_of_repr(monkeypatch):
    monkeypatch.setenv("AGRC_OLLAMA_API_KEY", "model-token")
    importlib.reload(config_module)
    try:
        settings = config_module.Settings()
        assert settings.ollama_api_key == "model-token"
        assert "model-token" not in repr(settings)
    finally:
        monkeypatch.delenv("AGRC_OLLAMA_API_KEY", raising=False)
        importlib.reload(config_module)


def _record_client_creation(monkeypatch):
    pytest.importorskip("ollama")
    import ollama

    created = []

    class FakeClient:
        def __init__(self, host=None, timeout=None, **kwargs):
            created.append({"host": host, **kwargs})

    monkeypatch.setattr(ollama, "Client", FakeClient)
    return created


@pytest.mark.parametrize("api_key", [None, "model-token"])
def test_ollama_llm_rejects_remote_http_before_creating_the_client(monkeypatch, api_key):
    created = _record_client_creation(monkeypatch)

    with pytest.raises(ValueError, match="must use HTTPS"):
        OllamaLLM(model_name="m", host="http://models.example.org", timeout_s=5.0, api_key=api_key)

    assert created == []


@pytest.mark.parametrize(
    "host", ["http://localhost:11434", "http://127.0.0.1:11434", "http://[::1]:11434"]
)
def test_ollama_llm_allows_loopback_http_without_a_key(monkeypatch, host):
    created = _record_client_creation(monkeypatch)

    OllamaLLM(model_name="m", host=host, timeout_s=5.0)

    assert created == [{"host": host}]


def test_ollama_llm_ignores_a_whitespace_only_key(monkeypatch):
    created = _record_client_creation(monkeypatch)

    OllamaLLM(model_name="m", host="https://models.example.org", timeout_s=5.0, api_key="   ")

    assert "headers" not in created[0]
