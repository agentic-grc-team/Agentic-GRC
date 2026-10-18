"""Saving the interview agent's results (AGRC-32), against PostgreSQL."""

import uuid

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from app.db.models import ControlResult, ControlResultReview, DecisionTraceRecord, OrganizationMembership
from app.schemas.agent_results import AgentControlResult
from app.schemas.decision_trace import DecisionTrace
from app.schemas.expert_review import ReviewDecision
from app.services.agent_results import save_agent_result
from app.services.expert_reviews import list_pending_reviews, save_review_decision
from tests.test_expert_review_db import db, make_assessment, make_control, make_organization, make_user  # noqa: F401


def agent_output(**changes) -> dict:
    """The `output` of a status_assessed trace, as the agent writes it (agentic_grc_agent ControlResult)."""
    output = {
        "question_code": "IAM-01",
        "control_ids": ["PR.AA-03"],
        "status": "implemented",
        "is_preliminary": True,
        "confidence": 0.9,
        "reason": "Affirmative answer with scope described; evidence was requested and is still to be validated.",
        "summary": "All administrator accounts in Microsoft 365 use MFA with Authenticator.",
        "follow_ups_used": 1,
        "requires_human_review": False,
        "evidence_pending": True,
        "supporting_turns": [2, 4],
    }
    output.update(changes)
    return output


def agent_trace(organization, assessment, result_output: dict, **changes) -> DecisionTrace:
    output = result_output
    fields = {
        "organization_id": organization.id,
        "assessment_id": assessment.id,
        "decision_type": "status_assessed",
        "control_ids": output["control_ids"],
        "module": "Identity and access management",
        "sources": [{"type": "interview_turn", "ref": "interview_turn:2", "excerpt": "Yes, all admins."}],
        "evidence_nature": "attestation",
        "actor_type": "agent",
        "prompt_id": "rule:yes_detailed",
        "prompt_version": "0.1.0",
        "kb_version": "demo-0.2",
        "output": output,
        "rationale": output["reason"],
        "confidence": output["confidence"],
        "requires_human_review": output["requires_human_review"],
    }
    fields.update(changes)
    return DecisionTrace(**fields)


def setup_assessment(db, codes=("PR.AA-03",), role="consultant"):
    organization = make_organization(db)
    user = make_user(db)
    db.add(OrganizationMembership(organization_id=organization.id, user_id=user.id, role=role, status="active"))
    db.commit()
    assessment = make_assessment(db, organization)
    controls = [make_control(db, organization, assessment, control_code=code) for code in codes]
    return organization, user, assessment, controls


def save(db, organization, assessment, result_output: dict, **trace_changes):
    result = AgentControlResult.from_agent_output(result_output)
    trace = agent_trace(organization, assessment, result_output, **trace_changes)
    return save_agent_result(db, organization.id, assessment.id, result, trace)


def test_saves_trace_and_result_together(db):
    organization, _, assessment, (control,) = setup_assessment(db)

    rows = save(db, organization, assessment, agent_output())
    db.commit()
    db.expire_all()

    row = db.get(ControlResult, rows[0].id)
    trace = db.get(DecisionTraceRecord, row.trace_id)
    assert row.assessment_control_id == control.id
    assert (row.version_no, row.author_actor, row.author_user_id) == (1, "agent", None)
    assert row.control_status == "implemented"
    assert row.explanation.startswith("All administrator accounts") and "evidence was requested" in row.explanation
    assert float(row.confidence) == 0.9
    assert row.evidence_pending is True and row.requires_human_review is False
    assert row.evidence_refs == [] and row.maturity_current is None
    assert trace.decision_type == "status_assessed" and trace.output["status"] == "implemented"


def test_only_flushes_so_the_caller_decides(db):
    organization, _, assessment, _ = setup_assessment(db)

    rows = save(db, organization, assessment, agent_output())
    result_id, trace_id = rows[0].id, rows[0].trace_id
    db.rollback()  # the caller gives up: nothing of the decision may remain

    assert db.get(ControlResult, result_id) is None
    assert db.get(DecisionTraceRecord, trace_id) is None


def test_one_row_per_control_sharing_one_trace(db):
    organization, _, assessment, controls = setup_assessment(db, codes=("PR.AA-01", "PR.AA-05"))

    rows = save(db, organization, assessment, agent_output(control_ids=["PR.AA-05", "PR.AA-01"]))

    assert [row.assessment_control_id for row in rows] == [controls[1].id, controls[0].id]
    assert len({row.trace_id for row in rows}) == 1


def test_not_applicable_and_not_assessed_fill_the_required_fields(db):
    organization, _, assessment, _ = setup_assessment(db, codes=("PR.AA-01", "PR.AA-03"))

    (na,) = save(db, organization, assessment, agent_output(
        control_ids=["PR.AA-01"], status="not_applicable", evidence_pending=False,
        summary="They have no on-premises servers.", reason="Not applicable, with a justification.",
    ), prompt_id="rule:na_justified")
    (unassessed,) = save(db, organization, assessment, agent_output(
        control_ids=["PR.AA-03"], status="not_assessed", evidence_pending=False, requires_human_review=True,
        summary="", reason="Nobody in the session could answer.",
    ), prompt_id="rule:unsure_limit")
    db.commit()

    assert na.justification == "They have no on-premises servers."
    assert unassessed.not_assessed_reason == "Nobody in the session could answer."


def test_draft_enters_the_review_queue_even_without_the_review_flag(db):
    organization, user, assessment, _ = setup_assessment(db)

    (row,) = save(db, organization, assessment, agent_output(requires_human_review=False))
    db.commit()

    queue = list_pending_reviews(db, user)
    assert [item.result_id for item in queue] == [str(row.id)]
    assert queue[0].requires_human_review is False


def test_agent_result_then_expert_review_is_saved(db):
    """The AGRC-32 done-when: agent result → saved → expert review → saved decision."""
    organization, user, assessment, _ = setup_assessment(db)

    (row,) = save(db, organization, assessment, agent_output())
    db.commit()
    review = save_review_decision(db, row.id, ReviewDecision(outcome="accepted", comment="Policy checked."), user)
    db.commit()
    db.expire_all()

    stored = db.get(ControlResultReview, review.id)
    review_trace = db.get(DecisionTraceRecord, stored.review_trace_id)
    assert stored.control_result_id == row.id and stored.outcome == "accepted"
    assert review_trace.reviews_trace_id == row.trace_id
    assert list_pending_reviews(db, user) == []


@pytest.mark.parametrize(
    "trace_changes, detail",
    [
        ({"decision_type": "answer_interpreted"}, "status_assessed"),
        ({"assessment_id": uuid.uuid4()}, "another organization or assessment"),
        ({"output": agent_output(status="not_implemented")}, "does not record this result"),
    ],
)
def test_refuses_a_trace_that_does_not_explain_the_result(db, trace_changes, detail):
    organization, _, assessment, _ = setup_assessment(db)

    with pytest.raises(HTTPException) as error:
        save(db, organization, assessment, agent_output(), **trace_changes)
    assert error.value.status_code == 409 and detail in error.value.detail


def test_refuses_a_control_that_is_not_in_the_assessment(db):
    organization, _, assessment, _ = setup_assessment(db, codes=("PR.AA-01",))

    with pytest.raises(HTTPException) as error:
        save(db, organization, assessment, agent_output(control_ids=["PR.AA-03"]))
    assert error.value.status_code == 409 and "PR.AA-03" in error.value.detail


def test_refuses_a_control_outside_the_scope(db):
    organization, _, assessment, _ = setup_assessment(db, codes=())
    make_control(db, organization, assessment, in_scope=False, scope_rationale="Excluded by the client.")

    with pytest.raises(HTTPException) as error:
        save(db, organization, assessment, agent_output())
    assert "outside the assessment scope" in error.value.detail


def test_refuses_a_second_result_for_the_same_control(db):
    organization, _, assessment, _ = setup_assessment(db)
    save(db, organization, assessment, agent_output())
    db.commit()

    with pytest.raises(HTTPException) as error:
        save(db, organization, assessment, agent_output())
    assert "already have a result" in error.value.detail


def test_refuses_an_assessment_of_another_organization(db):
    organization, _, assessment, _ = setup_assessment(db)
    other = make_organization(db)
    output = agent_output()
    trace = agent_trace(other, assessment, output)

    with pytest.raises(HTTPException) as error:
        save_agent_result(db, other.id, assessment.id, AgentControlResult.from_agent_output(output), trace)
    assert error.value.status_code == 404
    assert db.scalars(select(DecisionTraceRecord).where(DecisionTraceRecord.organization_id == other.id)).all() == []


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "not_applicable", "summary": ""},  # no justification
        {"status": "not_assessed", "reason": ""},  # no reason
        {"control_ids": []},
    ],
)
def test_contract_rejects_incomplete_agent_results(changes):
    with pytest.raises(ValidationError):
        AgentControlResult.from_agent_output(agent_output(**changes))
