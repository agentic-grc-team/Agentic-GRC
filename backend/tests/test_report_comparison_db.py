"""HU-24 (AGRC-144): which earlier assessments an assessment can be compared with (real PostgreSQL)."""

from datetime import datetime, timedelta, timezone

from app.services.reports.comparison import list_comparison_candidates
from tests.test_report_db_source import db, make_assessment, make_organization

T0 = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def _completed(db, organization, days: int, **changes):
    created = T0 + timedelta(days=days)
    fields = {
        "status": "completed",
        "started_at": created,
        "completed_at": created + timedelta(days=1),
        "created_at": created,
    }
    fields.update(changes)
    return make_assessment(db, organization, **fields)


def test_candidates_are_earlier_completed_assessments_of_the_same_organization(db):
    organization = make_organization(db)
    older = _completed(db, organization, days=0)
    newer = _completed(db, organization, days=10)
    not_completed = make_assessment(
        db, organization, status="awaiting_review", created_at=T0 + timedelta(days=20)
    )
    current = make_assessment(db, organization, status="in_progress", created_at=T0 + timedelta(days=30))
    later = _completed(db, organization, days=40)

    ids = [candidate.id for candidate in list_comparison_candidates(db, organization.id, current.id)]

    assert ids == [newer.id, older.id]  # most recently completed first
    assert not_completed.id not in ids
    assert later.id not in ids
    assert current.id not in ids


def test_candidates_never_include_another_organization(db):
    organization = make_organization(db)
    other = make_organization(db)
    foreign = _completed(db, other, days=0)
    current = make_assessment(db, organization, created_at=T0 + timedelta(days=30))

    assert list_comparison_candidates(db, organization.id, current.id) == []
    # Asking with the wrong organization for an assessment finds nothing either.
    assert list_comparison_candidates(db, other.id, current.id) == []
    assert foreign.id not in [c.id for c in list_comparison_candidates(db, other.id, foreign.id)]


def test_first_assessment_has_no_candidates(db):
    organization = make_organization(db)
    current = make_assessment(db, organization, created_at=T0)
    assert list_comparison_candidates(db, organization.id, current.id) == []


def test_candidate_carries_framework_and_kb_version(db):
    organization = make_organization(db)
    previous = _completed(db, organization, days=0, kb_version="kb-old")
    current = make_assessment(db, organization, created_at=T0 + timedelta(days=5))

    (candidate,) = list_comparison_candidates(db, organization.id, current.id)
    assert candidate.id == previous.id
    assert candidate.framework == "NIST CSF 2.0"
    assert candidate.kb_version == "kb-old"
    assert candidate.completed_at == previous.completed_at
