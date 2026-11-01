"""Review evidence normalization, authentication and access checks."""

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.v1.dependencies import get_db_session
from app.api.v1.endpoints import expert_reviews as endpoints
from app.main import app
from app.schemas.expert_review import ReviewEvidence
from app.security.auth import get_current_user
from app.services.review_evidence import (
    _source_entries,
    get_review_evidence,
)


def test_normalizes_result_and_trace_source_formats():
    sources, skipped = _source_entries([
        {
            "source_type": "document_span",
            "reference": "document_span:abc",
            "excerpt": "  Policy  ",
        },
        {
            "type": "interview_turn",
            "ref": "interview_turn:1",
            "excerpt": 42,
        },
        {
            "type": "tenant_configuration",
            "ref": "tenant:1",
        },
        None,
        {"reference": " "},
        "invalid",
    ])

    assert skipped == 3

    assert [source.source_type for source in sources] == [
        "document_span",
        "interview_turn",
        "other",
    ]

    assert sources[0].excerpt == "Policy"
    assert sources[1].excerpt is None
    assert all(source.document is None for source in sources)


@pytest.mark.parametrize("raw", [None, [], {}, "invalid"])
def test_handles_unstructured_source_json(raw):
    sources, skipped = _source_entries(raw)

    assert sources == []


@pytest.mark.parametrize(
    "membership, expected",
    [
        (None, 404),
        (SimpleNamespace(role="representative"), 403),
    ],
)
def test_checks_access_before_loading_evidence(membership, expected):
    db = Mock()
    db.get.return_value = SimpleNamespace(
        organization_id=uuid4(),
    )
    db.scalar.return_value = membership

    user = SimpleNamespace(
        id=uuid4(),
        is_platform_admin=False,
    )

    with pytest.raises(HTTPException) as error:
        get_review_evidence(db, uuid4(), user)

    assert error.value.status_code == expected
    db.scalars.assert_not_called()
    assert db.get.call_count == 1


@pytest.fixture
def api(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    db = Mock()

    monkeypatch.setitem(
        app.dependency_overrides,
        get_current_user,
        lambda: user,
    )

    monkeypatch.setitem(
        app.dependency_overrides,
        get_db_session,
        lambda: db,
    )

    service = Mock(
        return_value=ReviewEvidence(
            result_id=str(uuid4()),
            evidence_pending=True,
        )
    )

    monkeypatch.setattr(
        endpoints,
        "get_review_evidence",
        service,
    )

    return TestClient(app), user, db, service


def test_api_preserves_user_context_without_committing(api):
    client, user, db, service = api
    result_id = uuid4()

    response = client.get(
        f"/api/v1/expert-reviews/{result_id}/evidence"
    )

    assert response.status_code == 200
    assert response.json()["evidence_pending"] is True

    service.assert_called_once_with(db, result_id, user)
    db.commit.assert_not_called()


@pytest.mark.parametrize("status", [403, 404])
def test_api_preserves_access_denials(api, status):
    client, user, db, service = api

    service.side_effect = HTTPException(
        status_code=status,
        detail="Review unavailable.",
    )

    response = client.get(
        f"/api/v1/expert-reviews/{uuid4()}/evidence"
    )

    assert response.status_code == status


def test_api_requires_authentication(api, monkeypatch):
    client, user, db, service = api

    monkeypatch.delitem(
        app.dependency_overrides,
        get_current_user,
    )

    response = client.get(
        f"/api/v1/expert-reviews/{uuid4()}/evidence"
    )

    assert response.status_code in (401, 403)
    service.assert_not_called()
@pytest.mark.parametrize(
    "length, expected",
    [
        (999, "A" * 999),
        (1000, "A" * 1000),
        (1001, "A" * 997 + "..."),
    ],
    ids=["below-limit", "at-limit", "over-limit"],
)
def test_marks_only_truncated_excerpts(length, expected):
    sources, skipped = _source_entries([
        {
            "type": "interview_turn",
            "ref": "interview_turn:1",
            "excerpt": "  " + "A" * length + "  ",
        },
    ])

    assert skipped == 0
    assert sources[0].excerpt == expected
