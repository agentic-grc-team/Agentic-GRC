from decision_trace.models import DecisionTrace

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