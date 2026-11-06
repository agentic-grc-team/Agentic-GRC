import sys
from unittest.mock import MagicMock

from app.cli import main as cli_main
from app.core.config import Settings
import app.services.interview_agent as ia


def test_interview_service_builds_ollama_with_settings(monkeypatch):
    test_settings = Settings(
        _env_file=None,
        agrc_llm_keep_alive="10m",
        agrc_llm_num_predict=200,
    )
    monkeypatch.setattr(ia, "get_settings", lambda: test_settings)

    recorded_kwargs = []

    class RecorderOllama:
        def __init__(self, model_name, host, timeout_s, retries, keep_alive=None, num_predict=None):
            recorded_kwargs.append({"keep_alive": keep_alive, "num_predict": num_predict})
            self.model_name = model_name

    monkeypatch.setattr("app.agent.llm.OllamaLLM", RecorderOllama)
    mock_context = MagicMock()
    mock_context.knowledge_base = MagicMock()

    ia._build_graph(mock_context)

    assert len(recorded_kwargs) == 1
    assert recorded_kwargs[0]["keep_alive"] == "10m"
    assert recorded_kwargs[0]["num_predict"] == 200


SECRET = "sb_secret_must-not-be-printed"


def _cli_settings(monkeypatch):
    """Settings for the CLI tests: never read backend/.env, and carry a secret that must not be printed."""
    settings = Settings(
        _env_file=None,
        agrc_llm_model="llama3.1:8b",
        agrc_ollama_host="http://127.0.0.1:11434",
        agrc_llm_keep_alive="30m",
        db_password=SECRET,
        supabase_secret_key=SECRET,
    )
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)


def test_cli_warm_up_model_success(monkeypatch, capsys):
    class FakeOllama:
        def __init__(self, *args, **kwargs):
            pass

        def warm_up(self):
            return 123

    _cli_settings(monkeypatch)
    monkeypatch.setattr("app.agent.llm.OllamaLLM", FakeOllama)
    monkeypatch.setattr(sys, "argv", ["app.cli", "warm-up-model"])

    ret = cli_main()
    assert ret == 0
    out = capsys.readouterr().out
    assert out.strip() == "Model llama3.1:8b loaded in 123 ms (keep-alive 30m)."
    assert SECRET not in out


def test_cli_warm_up_model_failure(monkeypatch, capsys):
    class FakeOllama:
        def __init__(self, *args, **kwargs):
            pass

        def warm_up(self):
            return None

    _cli_settings(monkeypatch)
    monkeypatch.setattr("app.agent.llm.OllamaLLM", FakeOllama)
    monkeypatch.setattr(sys, "argv", ["app.cli", "warm-up-model"])

    ret = cli_main()
    assert ret == 1
    out = capsys.readouterr().out
    assert out.strip() == "Could not reach the model at http://127.0.0.1:11434. Is Ollama running?"
    assert SECRET not in out
