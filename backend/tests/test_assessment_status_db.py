"""Assessment status transitions driven by agent results and expert reviews, against PostgreSQL."""

from app.db.models import Assessment
from app.schemas.expert_review import ReviewDecision
from app.services.assessment_status import refresh_assessment_status
from app.services.expert_reviews import save_review_decision
from tests.test_agent_results_db import agent_output, save, setup_assessment
from tests.test_expert_review_db import db  # noqa: F401

CODES = ("PR.AA-01", "PR.AA-03")


def _status(db, assessment):
    db.expire_all()
    stored = db.get(Assessment, assessment.id)
    return stored.status, stored.completed_at


def _agent_result(db, organization, assessment, code):
    # save_agent_result refreshes the status itself.
    (row,) = save(db, organization, assessment, agent_output(control_ids=[code]))
    db.commit()
    return row


def test_status_moves_from_in_progress_to_awaiting_review_to_completed(db):
    organization, user, assessment, _ = setup_assessment(db, codes=CODES)

    first = _agent_result(db, organization, assessment, "PR.AA-01")
    assert _status(db, assessment) == ("in_progress", None)

    second = _agent_result(db, organization, assessment, "PR.AA-03")
    assert _status(db, assessment) == ("awaiting_review", None)

    save_review_decision(db, first.id, ReviewDecision(outcome="accepted", comment="Checked."), user)
    db.commit()
    assert _status(db, assessment) == ("awaiting_review", None)

    save_review_decision(
        db,
        second.id,
        ReviewDecision(
            outcome="modified",
            comment="Only some administrators use MFA.",
            modified_result={"control_status": "partially_implemented", "explanation": "MFA covers part of the admins."},
        ),
        user,
    )
    db.commit()
    status, completed_at = _status(db, assessment)
    assert status == "completed" and completed_at is not None


def test_a_rejected_result_keeps_the_assessment_awaiting_review(db):
    organization, user, assessment, _ = setup_assessment(db, codes=("PR.AA-03",))
    row = _agent_result(db, organization, assessment, "PR.AA-03")

    save_review_decision(db, row.id, ReviewDecision(outcome="rejected", comment="Wrong control."), user)
    db.commit()

    assert _status(db, assessment) == ("awaiting_review", None)


def test_a_later_agent_decision_does_not_reopen_a_completed_assessment(db):
    organization, user, assessment, _ = setup_assessment(db, codes=("PR.AA-03",))
    first = _agent_result(db, organization, assessment, "PR.AA-03")
    save_review_decision(db, first.id, ReviewDecision(outcome="accepted", comment="Confirmed."), user)
    db.commit()
    assert _status(db, assessment)[0] == "completed"

    # The expert's decision stays (#66): the agent only records its trace, so nothing reopens.
    assert save(db, organization, assessment, agent_output(summary="A later answer.")) == []
    refresh_assessment_status(db, organization.id, assessment.id)
    db.commit()

    assert _status(db, assessment)[0] == "completed"


def test_draft_assessments_are_never_moved(db):
    organization, _, assessment, _ = setup_assessment(db, codes=("PR.AA-03",))
    assessment.status = "draft"
    db.commit()

    _agent_result(db, organization, assessment, "PR.AA-03")

    assert _status(db, assessment) == ("draft", None)
