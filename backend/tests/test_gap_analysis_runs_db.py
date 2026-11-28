"""HU-16 run history and AGRC-121 acceptance checks against PostgreSQL."""

from sqlalchemy import select

from app.db.models import GapAnalysisRun
from app.schemas.expert_review import ReviewDecision
from app.services.assessment_status import refresh_assessment_status
from app.services.expert_reviews import save_review_decision
from app.services.gap_analysis_runs import list_gap_analysis_runs, record_gap_analysis_run, run_gap_list
from tests.test_agent_results_db import agent_output, save, setup_assessment
from tests.test_expert_review_db import db  # noqa: F401


def test_completion_and_regeneration_record_distinct_runs_without_duplicate_findings(db):
    organization, user, assessment, _ = setup_assessment(db, codes=("PR.AA-01", "PR.AA-03", "PR.AA-05"))
    outcomes = (
        ("PR.AA-01", "partially_implemented"),
        ("PR.AA-03", "not_implemented"),
        ("PR.AA-05", "not_applicable"),
    )
    for code, status in outcomes:
        (row,) = save(
            db,
            organization,
            assessment,
            agent_output(
                control_ids=[code],
                status=status,
                evidence_pending=False,
                summary=f"The {code} interview answer.",
            ),
        )
        save_review_decision(db, row.id, ReviewDecision(outcome="accepted", comment="Checked."), user)
    db.commit()

    runs = list_gap_analysis_runs(db, organization.id, assessment.id)
    assert len(runs) == 1
    assert runs[0].trigger == "completion"
    first_gaps = run_gap_list(runs[0]).gaps
    assert {gap.control_code for gap in first_gaps} == {"PR.AA-01", "PR.AA-03"}
    assert {gap.control_status for gap in first_gaps} == {"partially_implemented", "not_implemented"}
    assert all(gap.evidence or gap.evidence_absent for gap in first_gaps)
    assert len({gap.control_code for gap in first_gaps}) == len(first_gaps)

    refresh_assessment_status(db, organization.id, assessment.id)
    db.commit()
    assert len(list_gap_analysis_runs(db, organization.id, assessment.id)) == 1

    regenerated = record_gap_analysis_run(
        db, organization.id, assessment.id, trigger="regeneration", requested_by_user_id=user.id
    )
    db.commit()
    assert regenerated.requested_by_user_id == user.id
    assert regenerated.gap_count == 2
    assert len({gap.control_code for gap in run_gap_list(regenerated).gaps}) == 2
    assert len(list_gap_analysis_runs(db, organization.id, assessment.id)) == 2


def test_aborted_regeneration_leaves_no_partial_run(db):
    organization, user, assessment, _ = setup_assessment(db, codes=("PR.AA-03",))
    record_gap_analysis_run(db, organization.id, assessment.id, trigger="regeneration", requested_by_user_id=user.id)
    db.rollback()
    assert db.scalars(select(GapAnalysisRun).where(GapAnalysisRun.assessment_id == assessment.id)).all() == []
