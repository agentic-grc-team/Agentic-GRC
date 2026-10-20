"""Service integration: saved agent result -> review -> database report.

These tests do not run a live interview or browser workflow.
"""

from datetime import datetime, timezone

from app.db.models import (
    ControlResult,
    ControlResultReview,
    DecisionTraceRecord,
    OrganizationMembership,
)
from app.schemas.agent_results import AgentControlResult
from app.schemas.decision_trace import DecisionTrace
from app.schemas.expert_review import ReviewDecision
from app.services.agent_results import save_agent_result
from app.services.expert_reviews import (
    list_pending_reviews,
    save_review_decision,
)
from app.services.reports.builder import build_report_view
from app.services.reports.source import DbReportSource

from tests.test_report_db_source import (
    db,
    make_assessment,
    make_control,
    make_organization,
    make_user,
)

import pytest
from sqlalchemy import select


@pytest.mark.parametrize(
    "outcome",
    ["accepted", "modified", "rejected"],
)
def test_saved_agent_result_review_report_flow(db, outcome):
    organization = make_organization(db)
    reviewer = make_user(db)
    assessment = make_assessment(db, organization)
    control = make_control(db, organization, assessment)

    db.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=reviewer.id,
            role="consultant",
            status="active",
        )
    )
    db.commit()

    proposal = AgentControlResult(
        question_code="IAM-01",
        control_ids=[control.control_code],
        status="implemented",
        explanation="The participant reports MFA for all administrators.",
        confidence=0.9,
        requires_human_review=False,
        evidence_pending=True,
    )

    trace = DecisionTrace(
        organization_id=organization.id,
        assessment_id=assessment.id,
        decision_type="status_assessed",
        control_ids=[control.control_code],
        sources=[
            {
                "type": "interview_turn",
                "ref": "interview_turn:flow-test-1",
                "excerpt": "All administrators use MFA.",
            },
        ],
        evidence_nature="attestation",
        actor_type="agent",
        prompt_id="rule:yes_detailed",
        prompt_version="0.1.0",
        kb_version=assessment.kb_version,
        output={"status": proposal.status},
        rationale="The participant described MFA coverage.",
        confidence=proposal.confidence,
        requires_human_review=False,
    )

    rows = save_agent_result(
        db,
        organization.id,
        assessment.id,
        proposal,
        trace,
    )
    result_id = rows[0].id

    db.commit()
    db.expire_all()

    # Even without requires_human_review, the proposal is still a draft.
    queue = list_pending_reviews(db, reviewer)

    assert str(result_id) in [
        item.result_id for item in queue
    ]

    source = DbReportSource()
    report_input = source.load(
        db,
        organization.id,
        assessment.id,
    )

    assert report_input is not None

    before_review = build_report_view(
        report_input,
        datetime.now(timezone.utc),
    )

    assert before_review.results == []
    assert before_review.summary.finalized == 0

    assert [
        (item.code, item.reason)
        for item in before_review.pending
    ] == [
        (control.control_code, "awaiting_review"),
    ]

    # Submit a real review through the persistence service.
    decision_data = {
        "outcome": outcome,
        "comment": "Checked during the service integration test.",
    }

    if outcome == "modified":
        decision_data["modified_result"] = {
            "control_status": "partially_implemented",
            "explanation": "MFA covers only some administrator accounts.",
        }

    original_trace_id = rows[0].trace_id

    review = save_review_decision(
        db,
        result_id,
        ReviewDecision(**decision_data),
        reviewer,
    )
    review_id = review.id

    db.commit()
    db.expire_all()

    assert str(result_id) not in [
        item.result_id
        for item in list_pending_reviews(db, reviewer)
    ]

    saved_review = db.get(ControlResultReview, review_id)
    original_result = db.get(ControlResult, result_id)

    assert saved_review.reviewed_by_user_id == reviewer.id
    assert saved_review.reviewed_at is not None
    assert saved_review.outcome == outcome

    review_trace = db.get(
        DecisionTraceRecord,
        saved_review.review_trace_id,
    )

    assert review_trace.reviews_trace_id == original_trace_id
    assert review_trace.review_outcome == outcome
    assert review_trace.actor_user_id == reviewer.id

    # Every decision preserves the original agent proposal and sources.
    assert original_result.author_actor == "agent"
    assert original_result.version_no == 1
    assert original_result.control_status == "implemented"
    assert original_result.explanation == proposal.explanation
    assert original_result.trace_id == original_trace_id

    original_trace = db.get(
        DecisionTraceRecord,
        original_trace_id,
    )

    assert original_trace.sources == [
        source.model_dump(mode="json")
        for source in trace.sources
    ]

    versions = list(
        db.scalars(
            select(ControlResult)
            .where(
                ControlResult.organization_id == organization.id,
                ControlResult.assessment_id == assessment.id,
                ControlResult.assessment_control_id == control.id,
            )
            .order_by(ControlResult.version_no)
        )
    )

    report_input = source.load(
        db,
        organization.id,
        assessment.id,
    )

    assert report_input is not None

    after_review = build_report_view(
        report_input,
        datetime.now(timezone.utc),
    )

    assert after_review.is_demo_data is False

    if outcome == "rejected":
        assert len(versions) == 1
        assert saved_review.resulting_result_id is None

        assert after_review.results == []
        assert after_review.exclusions == []
        assert after_review.summary.finalized == 0

        assert [
            (item.code, item.reason)
            for item in after_review.pending
        ] == [
            (
                control.control_code,
                "rejected_awaiting_new_version",
            ),
        ]

    else:
        assert after_review.pending == []
        assert after_review.summary.finalized == 1
        assert len(after_review.results) == 1

        final_result = after_review.results[0]

        assert final_result.code == control.control_code
        assert final_result.evidence_pending is True
        assert after_review.summary.final_with_evidence_pending == 1

        if outcome == "accepted":
            assert len(versions) == 1
            assert saved_review.resulting_result_id is None

            assert final_result.control_status == "implemented"
            assert final_result.basis == "accepted_agent_result"
            assert final_result.explanation == proposal.explanation

        else:
            assert len(versions) == 2

            consultant_version = versions[1]

            assert consultant_version.id == saved_review.resulting_result_id
            assert consultant_version.based_on_result_id == result_id
            assert consultant_version.author_actor == "aligo_consultant"
            assert consultant_version.author_user_id == reviewer.id
            assert consultant_version.trace_id == review_trace.id
            assert consultant_version.evidence_refs == original_result.evidence_refs

            assert final_result.control_status == "partially_implemented"
            assert final_result.basis == "consultant_version"
            assert final_result.explanation == (
                "MFA covers only some administrator accounts."
            )