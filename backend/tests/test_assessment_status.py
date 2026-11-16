"""Assessment status follows its results: in_progress → awaiting_review → completed."""

import pytest

from app.services.assessment_status import accepts_interviews, derive_status


@pytest.mark.parametrize(
    "in_scope, with_result, final, expected",
    [
        (3, 0, 0, "in_progress"),
        (3, 2, 2, "in_progress"),
        (3, 3, 0, "awaiting_review"),
        (3, 3, 2, "awaiting_review"),
        (3, 3, 3, "completed"),
        (0, 0, 0, "in_progress"),
    ],
)
def test_derive_status(in_scope, with_result, final, expected):
    assert derive_status(in_scope, with_result, final) == expected


@pytest.mark.parametrize(
    "status, open_",
    [("draft", False), ("in_progress", True), ("awaiting_review", True), ("completed", False)],
)
def test_interviews_stay_open_until_completed(status, open_):
    assert accepts_interviews(status) is open_


def test_the_assessment_response_carries_the_interview_rule():
    from datetime import datetime, timezone
    from uuid import uuid4

    from app.schemas.assessments import AssessmentRead

    def read(assessment_status):
        return AssessmentRead(
            id=uuid4(),
            organization_id=uuid4(),
            title="Q4",
            framework_code="NIST-CSF",
            framework_version="2.0",
            kb_version="demo-0.2",
            status=assessment_status,
            created_by_user_id=None,
            started_at=None,
            completed_at=None,
            created_at=datetime.now(timezone.utc),
        ).model_dump()["accepts_interviews"]

    assert [read(s) for s in ("draft", "in_progress", "awaiting_review", "completed")] == [
        False,
        True,
        True,
        False,
    ]
