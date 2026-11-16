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
