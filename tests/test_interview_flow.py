"""End-to-end interview flow with a fake LLM (no Ollama needed)."""

from conftest import run_scripted

from agentic_grc_agent.fallback import heuristic_interpret
from agentic_grc_agent.llm import FakeLLM
from agentic_grc_agent.nodes import Deps, InterviewNodes
from agentic_grc_agent.schemas import AnswerInterpretation, Clarification, FollowUpQuestion
from agentic_grc_agent.trace import TraceRecorder
from agentic_grc_agent.nodes import initial_state


def scripted_interpretations(*interps):
    queue = list(interps)
    return lambda _user: queue.pop(0)


def I(**kw):  # noqa: E743
    base = dict(intent="answer", summary="summary", rationale="because", confidence=0.9, key_quote="yes")
    return AnswerInterpretation(**{**base, **kw})


def make(llm):
    tracer = TraceRecorder()
    return InterviewNodes(Deps(llm=llm, kb=pytest_kb(), tracer=tracer)), tracer


def pytest_kb():
    from conftest import ROOT
    from agentic_grc_agent.knowledge import load_kb
    return load_kb(ROOT / "agentic_grc_agent" / "data" / "kb_demo.yaml")


def test_vague_yes_then_detail_closes_as_implemented():
    llm = FakeLLM({
        "interpret_answer": scripted_interpretations(
            I(category="yes", specificity="vague"),
            I(category="yes", specificity="detailed", mentions_scope=True),
        ),
        "generate_follow_up": lambda _u: FollowUpQuestion(question="You said yes: which accounts does it apply to?"),
    })
    nodes, tracer = make(llm)
    s = run_scripted(nodes, initial_state("org", "a1", ["IAM-01"]), ["Yes", "All of the 365 admins, with Authenticator"])

    r = s["results"]["IAM-01"]
    assert r["status"] == "implemented" and r["follow_ups_used"] == 1
    assert r["supporting_turns"] == [2, 4]  # both participant turns support the result
    # the follow-up interpretation sees the whole dialogue about this question
    assert "Yes" in llm.calls[-1][1] and "Authenticator" in llm.calls[-1][1]
    kinds = [t.decision_type for t in tracer.records]
    assert kinds == ["answer_interpreted", "answer_interpreted", "status_assessed"]
    assert all(t.control_ids == ["PR.AA-03"] for t in tracer.records)


def test_three_vague_follow_ups_then_stops():
    llm = FakeLLM({
        "interpret_answer": lambda _u: I(category="yes", specificity="vague"),
        "generate_follow_up": lambda _u: FollowUpQuestion(question="Could you give more detail?"),
    })
    nodes, _ = make(llm)
    s = run_scripted(nodes, initial_state("org", "a1", ["IAM-01"]), ["yes", "yes", "yes", "yes"])
    r = s["results"]["IAM-01"]
    assert r["follow_ups_used"] == 3
    assert r["status"] == "not_assessed" and r["requires_human_review"]


def test_clarification_does_not_consume_follow_ups():
    llm = FakeLLM({
        "interpret_answer": scripted_interpretations(
            I(intent="clarification_request"), I(category="no"),
        ),
        "clarify_question": lambda _u: Clarification(explanation="It is an extra code on your phone."),
    })
    nodes, _ = make(llm)
    s = run_scripted(nodes, initial_state("org", "a1", ["IAM-01"]), ["what is that?", "No"])
    assert s["results"]["IAM-01"]["status"] == "not_implemented"
    assert s["results"]["IAM-01"]["follow_ups_used"] == 0
    assert any(t["turn_type"] == "clarification" for t in s["turns"])


def test_moves_to_next_question():
    llm = FakeLLM({"interpret_answer": lambda _u: I(category="no")})
    nodes, _ = make(llm)
    s = run_scripted(nodes, initial_state("org", "a1", ["IAM-01", "IAM-02"]), ["No", "No"])
    assert set(s["results"]) == {"IAM-01", "IAM-02"}
    assert s["pending_message"].startswith("Thank you")


def test_llm_down_degrades_to_heuristic_and_templates():
    down = lambda _u: RuntimeError("connection refused")  # noqa: E731
    llm = FakeLLM({"interpret_answer": down, "generate_follow_up": down})
    nodes, tracer = make(llm)
    s = run_scripted(nodes, initial_state("org", "a1", ["IAM-01"]), ["Yes"])
    assert "Yes" in s["pending_message"]  # template quotes the participant
    assert tracer.records[0].fallback_used and tracer.records[0].prompt_id == "rule:keyword_fallback"


def test_evidence_request_is_traced():
    llm = FakeLLM({
        "interpret_answer": lambda _u: I(category="yes", mentions_scope=True),
        "generate_follow_up": lambda _u: FollowUpQuestion(question="Could we see the conditional access policy?"),
    })
    nodes, tracer = make(llm)
    run_scripted(nodes, initial_state("org", "a1", ["IAM-01"]), ["Yes, all of them"])
    assert "evidence_requested" in [t.decision_type for t in tracer.records]


def test_heuristic_examples():
    assert heuristic_interpret("No, never").category.value == "no"
    assert heuristic_interpret("I don't know, the provider handles it").category.value == "unsure"
    assert heuristic_interpret("Only on some systems").category.value == "partial"
    assert heuristic_interpret("What does that mean?").intent.value == "clarification_request"
    assert heuristic_interpret("Yes, of course").category.value == "yes"
    assert heuristic_interpret("Not all of them").category.value == "partial"
    assert heuristic_interpret("I'm not sure").category.value == "unsure"
