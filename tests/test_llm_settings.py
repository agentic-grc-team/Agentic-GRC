import importlib
import pytest
from pydantic import BaseModel

import agentic_grc_agent.config as config_module
from agentic_grc_agent.llm import FakeLLM, OllamaLLM


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
