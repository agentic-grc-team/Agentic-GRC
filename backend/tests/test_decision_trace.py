from app.schemas.decision_trace import DecisionTrace
import pytest
from pydantic import ValidationError

def test_valid_agent_decision_is_created():
    # Arrange
    sources = [{"type": "interview_turn", "ref": "interview_turn:1", "excerpt": "MFA is on for admins"}]

    # Act
    trace = DecisionTrace(
        decision_type="answer_interpreted",
        actor_type="agent",
        sources=sources,
        rationale="The user confirmed MFA for admins.",
        model_name="test-model",
        prompt_version="0.1",
        confidence=0.9,
    )

    # Assert 
    assert trace.confidence == 0.9
    assert trace.actor_type == "agent"

def make_agent_trace(confidence):
    return DecisionTrace(
        decision_type="answer_interpreted",
        actor_type="agent",
        sources=[{"type": "interview_turn", "ref": "interview_turn:1", "excerpt": "x"}],
        rationale="r",
        model_name="test-model",
        prompt_version="0.1",
        confidence=confidence,
    )


def test_confidence_at_boundaries_is_accepted():
    assert make_agent_trace(0.0).confidence == 0.0
    assert make_agent_trace(1.0).confidence == 1.0


def test_confidence_above_one_is_rejected():
    with pytest.raises(ValidationError):
        make_agent_trace(1.01)


def test_confidence_below_zero_is_rejected():
    with pytest.raises(ValidationError):
        make_agent_trace(-0.01)