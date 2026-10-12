import uuid

import pytest
from pydantic import ValidationError

from app.schemas.decision_trace import DecisionTrace


def make_trace(**changes):
    """A valid LLM decision by the agent. Each test changes only what it checks."""
    fields = {
        "organization_id": uuid.uuid4(),
        "assessment_id": uuid.uuid4(),
        "decision_type": "answer_interpreted",
        "control_ids": ["PR.AA-03"],
        "module": "Access",
        "sources": [{"type": "interview_turn", "ref": "interview_turn:1", "excerpt": "MFA is on for admins"}],
        "actor_type": "agent",
        "model_name": "llama3.1:8b",
        "prompt_id": "interpret_answer",
        "prompt_version": "0.2.0",
        "kb_version": "csf2.0-kb-0.1",
        "output": {"category": "yes"},
        "rationale": "The user confirmed MFA for admins.",
        "confidence": 0.9,
    }
    fields.update(changes)
    return DecisionTrace(**fields)


def make_review(**changes):
    """A valid consultant review of an earlier decision."""
    fields = {
        "decision_type": "human_review",
        "actor_type": "aligo_consultant",
        "actor_user_id": uuid.uuid4(),
        "sources": [],
        "model_name": None,
        "prompt_id": None,
        "prompt_version": None,
        "confidence": None,
        "reviews_trace_id": uuid.uuid4(),
        "review_outcome": "accepted",
        "output": {},
        "rationale": "Agrees with the interview answer.",
    }
    fields.update(changes)
    return make_trace(**fields)


# --- normal cases -------------------------------------------------------------

def test_valid_llm_decision_is_created():
    # Arrange + Act
    trace = make_trace()

    # Assert
    assert trace.actor_type == "agent"
    assert trace.confidence == 0.9
    assert trace.sources[0].type == "interview_turn"


def test_rule_decision_without_model_is_accepted():
    trace = make_trace(decision_type="status_assessed", prompt_id="rule:close-on-no", model_name=None,
                       output={"status": "not_implemented"})
    assert trace.model_name is None


def test_valid_human_review_is_accepted():
    review = make_review(review_outcome="modified", output={"status": "partially_implemented"})
    assert review.review_outcome == "modified"


# --- boundary values ----------------------------------------------------------

def test_confidence_at_boundaries_is_accepted():
    assert make_trace(confidence=0.0).confidence == 0.0
    assert make_trace(confidence=1.0).confidence == 1.0


def test_confidence_above_one_is_rejected():
    with pytest.raises(ValidationError):
        make_trace(confidence=1.01)


def test_confidence_below_zero_is_rejected():
    with pytest.raises(ValidationError):
        make_trace(confidence=-0.01)


def test_negative_latency_is_rejected():
    with pytest.raises(ValidationError):
        make_trace(latency_ms=-1)


# --- rules that must fail -----------------------------------------------------

def test_unknown_decision_type_is_rejected():
    with pytest.raises(ValidationError):
        make_trace(decision_type="guessed")


def test_agent_decision_without_sources_is_rejected():
    with pytest.raises(ValidationError, match="at least one source"):
        make_trace(sources=[])


def test_llm_decision_without_model_is_rejected():
    with pytest.raises(ValidationError, match="model_name"):
        make_trace(model_name=None)


def test_agent_decision_without_prompt_is_rejected():
    with pytest.raises(ValidationError, match="prompt_id"):
        make_trace(prompt_id=None)


def test_review_by_agent_is_rejected():
    with pytest.raises(ValidationError, match="never by the agent"):
        make_review(actor_type="agent", actor_user_id=None, prompt_id="rule:x", prompt_version="0.1",
                    sources=[{"type": "interview_turn", "ref": "interview_turn:1"}])


def test_human_decision_without_user_is_rejected():
    with pytest.raises(ValidationError, match="must record actor_user_id"):
        make_review(actor_user_id=None)


def test_agent_decision_with_user_is_rejected():
    with pytest.raises(ValidationError, match="agent decision has no actor_user_id"):
        make_trace(actor_user_id=uuid.uuid4())


def test_review_without_reviewed_trace_is_rejected():
    with pytest.raises(ValidationError, match="reviews_trace_id"):
        make_review(reviews_trace_id=None)


def test_human_decision_with_confidence_is_rejected():
    with pytest.raises(ValidationError, match="no confidence"):
        make_review(confidence=0.8)


def test_fallback_interpretation_without_review_is_accepted():
    # A fallback that only leads to a follow-up question does not need review (schema v0.2, review on PR #9).
    trace = make_trace(fallback_used=True, requires_human_review=False, prompt_id="rule:keyword_fallback", model_name=None)
    assert trace.fallback_used is True


def test_control_closed_on_fallback_without_review_is_rejected():
    with pytest.raises(ValidationError, match="fallback"):
        make_trace(decision_type="status_assessed", output={"status": "implemented"},
                   fallback_used=True, requires_human_review=False)


@pytest.mark.parametrize("status", ["implemented", "partially_implemented", "not_implemented", "not_applicable", "not_assessed"])
def test_every_control_status_is_accepted(status):
    trace = make_trace(decision_type="status_assessed", prompt_id="rule:x", model_name=None, output={"status": status})
    assert trace.output["status"] == status


def test_unknown_control_status_is_rejected():
    with pytest.raises(ValidationError, match="output.status"):
        make_trace(decision_type="status_assessed", prompt_id="rule:x", model_name=None, output={"status": "Partially"})


def test_insufficient_evidence_without_human_review_is_rejected():
    with pytest.raises(ValidationError, match="Insufficient evidence"):
        make_trace(decision_type="evidence_validated", output={"state": "provided_insufficient"})
