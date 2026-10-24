import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.benchmark_models import percentile, summarize_latencies


def test_percentile_empty():
    assert percentile([], 0.5) == 0
    assert percentile([], 0.95) == 0


def test_percentile_values():
    assert percentile([1000, 2000, 3000], 0.5) == 2000
    assert percentile([1000, 2000, 3000], 0.95) == 3000


def test_summarize_latencies():
    stats = summarize_latencies([1000, 2000, 3000], [1000, 11000, 12000])
    assert stats["call_p50"] == 2000
    assert stats["call_p95"] == 3000
    assert stats["turn_p50"] == 11000
    assert stats["turn_p95"] == 12000
    assert stats["turns_over_10s"] == 2
    assert stats["call"]["p50"] == 2000
    assert stats["call"]["p95"] == 3000
    assert stats["turn"]["p50"] == 11000
    assert stats["turn"]["p95"] == 12000


def test_summarize_latencies_empty():
    stats = summarize_latencies([], [])
    assert stats["call_p50"] == 0
    assert stats["call_p95"] == 0
    assert stats["turn_p50"] == 0
    assert stats["turn_p95"] == 0
    assert stats["turns_over_10s"] == 0
    assert stats["turns_over_10s_pct"] == 0.0
    assert stats["call"]["p50"] == 0
    assert stats["turn"]["p50"] == 0


def test_turn_latency_adds_an_llm_call_only_when_the_real_flow_makes_one(monkeypatch):
    """Evidence requests use the template (no second call); other follow-ups and clarifications add one."""
    import time

    import scripts.benchmark_models as bm
    from agentic_grc_agent import prompts
    from agentic_grc_agent.config import Settings
    from agentic_grc_agent.knowledge import load_kb
    from agentic_grc_agent.llm import CallMeta, LLMError
    from agentic_grc_agent.schemas import AnswerInterpretation

    base = dict(summary="s", key_quote="we use MFA", rationale="r", confidence=0.9)
    interpretations = [
        AnswerInterpretation(**base, intent="answer", category="yes", specificity="detailed", mentions_scope=True),
        AnswerInterpretation(**base, intent="answer", category="yes", specificity="vague"),
        AnswerInterpretation(**base, intent="clarification_request"),
        AnswerInterpretation(**base, intent="answer", category="no", specificity="detailed"),
        AnswerInterpretation(**base, intent="off_topic"),
    ]
    latency = {prompts.INTERPRET_ID: 1000, prompts.FOLLOW_UP_ID: 300, prompts.CLARIFY_ID: 200}
    calls = []

    class FakeOllama:
        def __init__(self, model, host, timeout_s, retries=1, keep_alive="30m", num_predict=320):
            self.model_name = model
            self._interpretations = iter(interpretations)
            self._follow_ups = 0

        def warm_up(self):
            return 5

        def structured(self, *, prompt_id, prompt_version, system, user, schema):
            calls.append(prompt_id)
            if prompt_id == prompts.INTERPRET_ID:
                obj = next(self._interpretations)
            else:
                if prompt_id == prompts.FOLLOW_UP_ID:
                    self._follow_ups += 1
                    if self._follow_ups == 2:  # the off-topic redirect times out after 50 ms
                        time.sleep(0.05)
                        raise LLMError("simulated timeout")
                obj = schema.model_construct(**{name: "x?" for name in schema.model_fields})
            return obj, CallMeta(self.model_name, prompt_id, prompt_version, latency[prompt_id], 1)

    monkeypatch.setattr(bm, "OllamaLLM", FakeOllama)
    settings = Settings()
    case = {"question": "IAM-01", "dialogue": [{"participant": "answer"}], "expected": {}}
    cases = [dict(case, id=f"case-{n}") for n in range(len(interpretations))]

    result = bm.run_model("fake", cases, load_kb(settings.kb_path), settings)

    turns = [row["turn_latency_ms"] for row in result["rows"]]
    assert turns[0] == 1000  # evidence request: template, no second call
    assert turns[1] == 1300  # scope follow-up: + generate_follow_up
    assert turns[2] == 1200  # clarification: + clarify
    assert turns[3] == 1000  # close: no second call
    assert turns[4] >= 1050  # failed redirect follow-up: its elapsed time still counts
    assert calls.count(prompts.FOLLOW_UP_ID) == 2
    assert calls.count(prompts.CLARIFY_ID) == 1
    assert result["invalid_or_failed"] == 1
    assert result["cold_load_ms"] == 5
