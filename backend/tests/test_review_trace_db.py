"""Reasoning trace of one result in Expert reviews: context, steps and access (HU-25, AGRC-60)."""

from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.v1.dependencies import get_db_session
from app.db.models import ControlResult, OrganizationMembership
from app.main import app
from app.schemas.expert_review import ReviewDecision
from app.security.auth import get_current_user
from app.services.expert_reviews import save_review_decision
from app.services.review_trace import get_result_trace
from tests.test_expert_review_db import (
    db,  # noqa: F401  (pytest fixture)
    make_assessment,
    make_assessment_context,
    make_result,
    make_review_context,
    make_trace,
    make_user,
)


def call_endpoint(db, monkeypatch, user, result_id):
    monkeypatch.setitem(app.dependency_overrides, get_db_session, lambda: db)
    monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: user)
    return TestClient(app).get(f"/api/v1/expert-reviews/{result_id}/trace")


def test_trace_identifies_the_result_and_its_own_decision(db):
    organization, user, assessment, control, result, trace = make_review_context(db)

    view = get_result_trace(db, result.id, user)

    assert view.result_id == result.id
    assert view.organization_id == organization.id
    assert view.organization_name == organization.name
    assert view.assessment_id == assessment.id
    assert view.assessment_title == assessment.title
    assert view.control_code == "PR.AA-03"
    assert view.control_title == control.control_title
    assert view.result_version == 1
    assert view.result_author == "agent"
    assert view.result_trace_id == trace.id
    assert [step.id for step in view.steps] == [trace.id]
    assert view.steps[0].sources[0].ref == "interview_turn:1"


def test_steps_are_this_controls_decisions_in_order(db):
    organization, user, assessment, control = make_assessment_context(db)
    interpreted = make_trace(
        db, organization, assessment,
        decision_type="answer_interpreted", output={"intent": "partial"},
    )
    requested = make_trace(
        db, organization, assessment,
        decision_type="evidence_requested", output={"message": "Please share the policy."},
    )
    closed = make_trace(db, organization, assessment, output={"status": "partially_implemented"})
    other_control = make_trace(db, organization, assessment, control_ids=["PR.AA-01"])
    other_assessment = make_trace(db, organization, make_assessment(db, organization))
    result = make_result(db, organization, control, trace_id=closed.id)

    view = get_result_trace(db, result.id, user)

    assert [step.id for step in view.steps] == [interpreted.id, requested.id, closed.id]
    assert other_control.id not in [step.id for step in view.steps]
    assert other_assessment.id not in [step.id for step in view.steps]
    assert view.result_trace_id == closed.id


def test_review_decision_appears_after_the_agent_decision(db):
    organization, user, assessment, control, result, trace = make_review_context(db)
    save_review_decision(db, result.id, ReviewDecision(outcome="accepted", comment=""), user)
    db.commit()

    view = get_result_trace(db, result.id, user)

    assert [step.decision_type for step in view.steps] == ["status_assessed", "human_review"]
    assert view.steps[1].reviews_trace_id == trace.id
    assert view.result_trace_id == trace.id


def test_consultant_version_points_to_its_own_review_decision(db):
    organization, user, assessment, control, result, trace = make_review_context(db)
    review = save_review_decision(
        db,
        result.id,
        ReviewDecision(
            outcome="modified",
            comment="Admin accounts are not covered.",
            modified_result={"control_status": "not_implemented", "explanation": "MFA is not enforced."},
        ),
        user,
    )
    new_result_id = review.resulting_result_id
    db.commit()
    new_result = db.get(ControlResult, new_result_id)

    view = get_result_trace(db, new_result.id, user)

    assert view.result_version == 2
    assert view.result_author == "aligo_consultant"
    assert view.result_trace_id == new_result.trace_id
    assert view.result_trace_id != trace.id
    assert view.result_trace_id in [step.id for step in view.steps]


def test_result_without_a_decision_has_no_trace_and_none_is_invented(db):
    organization, user, assessment, control = make_assessment_context(db)
    result = make_result(db, organization, control, trace_id=None)

    view = get_result_trace(db, result.id, user)

    assert view.result_trace_id is None
    assert view.steps == []


def test_own_decision_is_included_even_if_its_control_list_differs(db):
    organization, user, assessment, control = make_assessment_context(db)
    trace = make_trace(db, organization, assessment, control_ids=["PR.AA-01"])
    result = make_result(db, organization, control, trace_id=trace.id)

    view = get_result_trace(db, result.id, user)

    assert [step.id for step in view.steps] == [trace.id]


def test_decisions_of_another_organization_are_never_included(db):
    organization, user, assessment, control, result, trace = make_review_context(db)
    other_org, _, other_assessment, _ = make_assessment_context(db)
    foreign = make_trace(db, other_org, other_assessment)

    view = get_result_trace(db, result.id, user)

    assert foreign.id not in [step.id for step in view.steps]


def test_unknown_result_is_not_found(db):
    _, user, _, _, _, _ = make_review_context(db)

    with pytest.raises(HTTPException) as error:
        get_result_trace(db, uuid4(), user)

    assert error.value.status_code == 404


def test_endpoint_returns_the_trace_to_a_consultant(db, monkeypatch):
    _, user, _, _, result, trace = make_review_context(db)

    response = call_endpoint(db, monkeypatch, user, result.id)

    assert response.status_code == 200
    body = response.json()
    assert body["result_trace_id"] == str(trace.id)
    assert [step["id"] for step in body["steps"]] == [str(trace.id)]


def test_endpoint_lets_a_platform_admin_read_without_membership(db, monkeypatch):
    _, _, _, _, result, _ = make_review_context(db)
    admin = make_user(db)
    admin.is_platform_admin = True
    db.commit()

    response = call_endpoint(db, monkeypatch, admin, result.id)

    assert response.status_code == 200


@pytest.mark.parametrize("role", ["representative", "foreign_consultant"])
def test_endpoint_denies_other_roles_and_tenants_without_trace_data(db, monkeypatch, role):
    organization, _, _, _, result, _ = make_review_context(db)
    if role == "representative":
        user = make_user(db)
        db.add(
            OrganizationMembership(
                organization_id=organization.id, user_id=user.id, role="representative", status="active"
            )
        )
        db.commit()
        expected = 403
    else:
        _, user, _, _, _, _ = make_review_context(db)
        expected = 404

    response = call_endpoint(db, monkeypatch, user, result.id)

    assert response.status_code == expected
    assert "steps" not in response.json()


def test_endpoint_requires_login(db, monkeypatch):
    _, _, _, _, result, _ = make_review_context(db)
    monkeypatch.setitem(app.dependency_overrides, get_db_session, lambda: db)
    monkeypatch.delitem(app.dependency_overrides, get_current_user, raising=False)

    response = TestClient(app).get(f"/api/v1/expert-reviews/{result.id}/trace")

    assert response.status_code == 401
