from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.services.expert_reviews import load_reviewable_result

from app.db.models import (
    Assessment,
    AssessmentControl,
    DecisionTraceRecord,
)
from app.schemas.expert_review import ReviewDecision
from app.services.expert_reviews import save_review_decision


@pytest.fixture
def review_context(monkeypatch):
    result = SimpleNamespace(
        id=uuid4(),
        organization_id=uuid4(),
        assessment_id=uuid4(),
        assessment_control_id=uuid4(),
        author_actor="agent",
    )

    control = SimpleNamespace(
        id=result.assessment_control_id,
        in_scope=True,
    )

    user = SimpleNamespace(id=uuid4())

    db = Mock(spec=Session)
    db.get.return_value = result
    db.scalar.side_effect = [
        control,
        result.id,
        None,
    ]

    access_check = Mock()
    monkeypatch.setattr(
        "app.services.expert_reviews.require_expert_review_access",
        access_check,
    )

    return SimpleNamespace(
        db=db,
        result=result,
        control=control,
        user=user,
        access_check=access_check,
    )


def test_loads_latest_unreviewed_agent_result(review_context):
    context = review_context

    result = load_reviewable_result(
        context.db,
        context.result.id,
        context.user,
    )

    assert result is context.result
    context.access_check.assert_called_once_with(
        context.db,
        context.result.organization_id,
        context.user,
    )
    context.db.commit.assert_not_called()


def test_rejects_unknown_result(review_context):
    context = review_context
    context.db.get.return_value = None

    with pytest.raises(HTTPException) as error:
        load_reviewable_result(
            context.db,
            uuid4(),
            context.user,
        )

    assert error.value.status_code == 404
    assert error.value.detail == "Review result not found."
    context.access_check.assert_not_called()
    context.db.scalar.assert_not_called()


def test_stops_when_access_is_denied(review_context):
    context = review_context
    context.access_check.side_effect = HTTPException(
        status_code=403,
        detail="Administrator or consultant access required.",
    )

    with pytest.raises(HTTPException) as error:
        load_reviewable_result(
            context.db,
            context.result.id,
            context.user,
        )

    assert error.value.status_code == 403
    context.db.scalar.assert_not_called()


def test_rejects_missing_control(review_context):
    context = review_context
    context.db.scalar.side_effect = [None]

    with pytest.raises(HTTPException) as error:
        load_reviewable_result(
            context.db,
            context.result.id,
            context.user,
        )

    assert error.value.status_code == 404
    assert error.value.detail == "Assessment control not found."


def test_rejects_out_of_scope_control(review_context):
    context = review_context
    context.control.in_scope = False

    with pytest.raises(HTTPException) as error:
        load_reviewable_result(
            context.db,
            context.result.id,
            context.user,
        )

    assert error.value.status_code == 409
    assert error.value.detail == (
        "This control is outside the assessment scope."
    )


def test_rejects_consultant_authored_result(review_context):
    context = review_context
    context.result.author_actor = "aligo_consultant"

    with pytest.raises(HTTPException) as error:
        load_reviewable_result(
            context.db,
            context.result.id,
            context.user,
        )

    assert error.value.status_code == 409
    assert error.value.detail == (
        "Only agent-authored results can be reviewed."
    )


def test_rejects_superseded_result(review_context):
    context = review_context
    context.db.scalar.side_effect = [
        context.control,
        uuid4(),
    ]

    with pytest.raises(HTTPException) as error:
        load_reviewable_result(
            context.db,
            context.result.id,
            context.user,
        )

    assert error.value.status_code == 409
    assert error.value.detail == (
        "This result has been superseded by a newer version."
    )


def test_rejects_already_reviewed_result(review_context):
    context = review_context
    context.db.scalar.side_effect = [
        context.control,
        context.result.id,
        uuid4(),
    ]

    with pytest.raises(HTTPException) as error:
        load_reviewable_result(
            context.db,
            context.result.id,
            context.user,
        )

    assert error.value.status_code == 409
    assert error.value.detail == (
        "This result has already been reviewed."
    )

@pytest.fixture
def persistence_context(monkeypatch):
    organization_id = uuid4()
    assessment_id = uuid4()
    control_id = uuid4()
    trace_id = uuid4()

    result = SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        assessment_id=assessment_id,
        assessment_control_id=control_id,
        trace_id=trace_id,
        version_no=1,
        maturity_current=2,
        maturity_target=4,
        evidence_pending=True,
        evidence_summary="MFA configuration evidence.",
        evidence_refs=[
            {
                "source_type": "document_span",
                "reference": "doc:1",
                "nature": "implementation",
            }
        ],
    )

    assessment = SimpleNamespace(
        id=assessment_id,
        organization_id=organization_id,
        kb_version="test-kb-1",
    )

    control = SimpleNamespace(
        id=control_id,
        organization_id=organization_id,
        assessment_id=assessment_id,
        control_code="PR.AA-03",
    )

    original_trace = SimpleNamespace(
        id=trace_id,
        organization_id=organization_id,
        assessment_id=assessment_id,
        actor_type="agent",
        decision_type="status_assessed",
        control_ids=["PR.AA-03"],
    )

    user = SimpleNamespace(id=uuid4())
    db = Mock(spec=Session)

    def fake_get(model, record_id):
        if model is Assessment and record_id == assessment.id:
            return assessment

        if model is AssessmentControl and record_id == control.id:
            return control

        if model is DecisionTraceRecord and record_id == original_trace.id:
            return original_trace

        return None

    db.get.side_effect = fake_get

    load_result = Mock(return_value=result)
    monkeypatch.setattr(
        "app.services.expert_reviews.load_reviewable_result",
        load_result,
    )

    saved_trace = SimpleNamespace(id=uuid4())
    save_trace = Mock(return_value=saved_trace)
    monkeypatch.setattr(
        "app.services.expert_reviews.record_trace",
        save_trace,
    )

    return SimpleNamespace(
        db=db,
        result=result,
        assessment=assessment,
        control=control,
        original_trace=original_trace,
        user=user,
        saved_trace=saved_trace,
        save_trace=save_trace,
        load_result=load_result,
    )


@pytest.mark.parametrize("outcome", ["accepted", "rejected"])
def test_saves_review_and_matching_human_trace(
    persistence_context,
    outcome,
):
    context = persistence_context
    decision = ReviewDecision(
        outcome=outcome,
        comment="  Evidence checked.  ",
    )

    review = save_review_decision(
        context.db,
        context.result.id,
        decision,
        context.user,
    )

    assert review.control_result_id == context.result.id
    assert review.organization_id == context.result.organization_id
    assert review.assessment_id == context.result.assessment_id
    assert review.outcome == outcome
    assert review.comment == "Evidence checked."
    assert review.reviewed_by_user_id == context.user.id
    assert review.review_trace_id == context.saved_trace.id
    assert review.resulting_result_id is None

    context.load_result.assert_called_once_with(
        context.db,
        context.result.id,
        context.user,
    )

    context.save_trace.assert_called_once()
    trace_db, trace = context.save_trace.call_args.args

    assert trace_db is context.db
    assert trace.decision_type == "human_review"
    assert trace.actor_type == "aligo_consultant"
    assert trace.actor_user_id == context.user.id
    assert trace.organization_id == context.result.organization_id
    assert trace.assessment_id == context.result.assessment_id
    assert trace.control_ids == ["PR.AA-03"]
    assert trace.kb_version == context.assessment.kb_version
    assert trace.reviews_trace_id == context.original_trace.id
    assert trace.review_outcome == outcome
    assert trace.output["control_result_review_id"] == str(review.id)

    context.db.add.assert_called_once_with(review)
    context.db.flush.assert_called_once()
    context.db.commit.assert_not_called()


def test_accept_without_comment_has_audit_rationale(
    persistence_context,
):
    context = persistence_context

    save_review_decision(
        context.db,
        context.result.id,
        ReviewDecision(outcome="accepted"),
        context.user,
    )

    trace = context.save_trace.call_args.args[1]

    assert trace.rationale == (
        "The reviewer accepted the proposed result."
    )
    assert trace.output["comment"] == ""


def test_rejects_result_without_original_trace(persistence_context):
    context = persistence_context
    context.result.trace_id = None

    with pytest.raises(HTTPException) as error:
        save_review_decision(
            context.db,
            context.result.id,
            ReviewDecision(outcome="accepted"),
            context.user,
        )

    assert error.value.status_code == 409
    context.save_trace.assert_not_called()
    context.db.add.assert_not_called()


@pytest.mark.parametrize(
    "field,value",
    [
        ("organization_id", uuid4()),
        ("assessment_id", uuid4()),
        ("actor_type", "aligo_consultant"),
        ("decision_type", "answer_interpreted"),
        ("control_ids", ["PR.AA-05"]),
    ],
)
def test_rejects_mismatched_original_trace(
    persistence_context,
    field,
    value,
):
    context = persistence_context
    setattr(context.original_trace, field, value)

    with pytest.raises(HTTPException) as error:
        save_review_decision(
            context.db,
            context.result.id,
            ReviewDecision(outcome="accepted"),
            context.user,
        )

    assert error.value.status_code == 409
    context.save_trace.assert_not_called()
    context.db.add.assert_not_called()


def test_does_not_add_review_when_trace_creation_fails(
    persistence_context,
):
    context = persistence_context
    context.save_trace.side_effect = RuntimeError(
        "Trace persistence failed."
    )

    with pytest.raises(RuntimeError, match="Trace persistence failed"):
        save_review_decision(
            context.db,
            context.result.id,
            ReviewDecision(outcome="accepted"),
            context.user,
        )

    context.db.add.assert_not_called()
    context.db.commit.assert_not_called()

def test_modified_review_creates_consultant_version(
    persistence_context,
):
    context = persistence_context

    decision = ReviewDecision(
        outcome="modified",
        comment="Corrected after checking the evidence.",
        modified_result={
            "control_status": "not_implemented",
            "explanation": "Privileged accounts do not enforce MFA.",
        },
    )

    review = save_review_decision(
        context.db,
        context.result.id,
        decision,
        context.user,
    )

    assert context.db.add.call_count == 2

    new_result = context.db.add.call_args_list[0].args[0]
    saved_review = context.db.add.call_args_list[1].args[0]

    assert saved_review is review
    assert new_result.id == review.resulting_result_id
    assert new_result.id != context.result.id
    assert new_result.organization_id == context.result.organization_id
    assert new_result.assessment_id == context.result.assessment_id
    assert new_result.assessment_control_id == (
        context.result.assessment_control_id
    )
    assert new_result.version_no == 2
    assert new_result.based_on_result_id == context.result.id
    assert new_result.author_actor == "aligo_consultant"
    assert new_result.author_user_id == context.user.id
    assert new_result.control_status == "not_implemented"
    assert new_result.explanation == (
        "Privileged accounts do not enforce MFA."
    )
    assert new_result.confidence is None
    assert new_result.maturity_current == 2
    assert new_result.maturity_target == 4
    assert new_result.evidence_pending is True
    assert new_result.evidence_refs == context.result.evidence_refs
    assert new_result.evidence_refs is not context.result.evidence_refs
    assert new_result.trace_id == context.saved_trace.id
    assert new_result.justification is None
    assert new_result.not_assessed_reason is None

    trace = context.save_trace.call_args.args[1]

    assert trace.review_outcome == "modified"
    assert trace.output["resulting_result_id"] == str(new_result.id)
    assert trace.output["modified_result"]["control_status"] == (
        "not_implemented"
    )

    assert context.result.version_no == 1
    context.db.flush.assert_called()
    context.db.commit.assert_not_called()


@pytest.mark.parametrize(
    "control_status,reason_field",
    [
        ("not_applicable", "justification"),
        ("not_assessed", "not_assessed_reason"),
    ],
)
def test_modified_version_preserves_required_reason(
    persistence_context,
    control_status,
    reason_field,
):
    context = persistence_context

    modified_result = {
        "control_status": control_status,
        "explanation": "Consultant explanation.",
        reason_field: "Confirmed reason.",
    }

    save_review_decision(
        context.db,
        context.result.id,
        ReviewDecision(
            outcome="modified",
            comment="Updated after review.",
            modified_result=modified_result,
        ),
        context.user,
    )

    new_result = context.db.add.call_args_list[0].args[0]

    assert getattr(new_result, reason_field) == "Confirmed reason."