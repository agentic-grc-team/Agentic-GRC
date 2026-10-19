"""Evidence-to-control link endpoints and reference helpers, without a database."""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.v1.dependencies import get_db_session
from app.main import app
from app.security.auth import get_current_user
from app.services.evidence_links import (
    ControlNotFoundError,
    EvidenceAssessmentMismatchError,
    EvidenceNotFoundError,
    document_reference,
    evidence_file_id_from_reference,
)

ENDPOINT = "app.api.v1.endpoints.evidence"
ORG_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
EVIDENCE_ID = uuid.uuid4()
CONTROL_ID = uuid.uuid4()
ASSESSMENT_ID = uuid.uuid4()


@pytest.fixture
def client(monkeypatch):
    saved = dict(app.dependency_overrides)
    app.dependency_overrides[get_db_session] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=USER_ID)
    monkeypatch.setattr(f"{ENDPOINT}._active_membership", lambda db, org_id, user_id: object() if org_id == ORG_ID else None)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved)


def fake_link():
    return SimpleNamespace(
        id=uuid.uuid4(),
        organization_id=ORG_ID,
        assessment_id=ASSESSMENT_ID,
        assessment_control_id=CONTROL_ID,
        evidence_file_id=EVIDENCE_ID,
        linked_by_user_id=USER_ID,
        created_at=datetime.now(timezone.utc),
    )


def post_link(client, evidence_id=EVIDENCE_ID, organization_id=ORG_ID):
    return client.post(
        f"/api/v1/evidence/{evidence_id}/controls",
        json={"organization_id": str(organization_id), "assessment_control_id": str(CONTROL_ID)},
    )


def test_link_requires_membership(client, monkeypatch):
    monkeypatch.setattr(f"{ENDPOINT}.link_evidence_to_control", lambda *args: pytest.fail("must not be called"))

    assert post_link(client, organization_id=uuid.uuid4()).status_code == 403


def test_new_link_returns_201_with_document_reference(client, monkeypatch):
    seen = []

    def fake_link_service(db, organization_id, evidence_file_id, assessment_control_id, linked_by_user_id):
        seen.append((organization_id, evidence_file_id, assessment_control_id, linked_by_user_id))
        return fake_link(), True

    monkeypatch.setattr(f"{ENDPOINT}.link_evidence_to_control", fake_link_service)

    response = post_link(client)

    assert response.status_code == 201
    assert seen == [(ORG_ID, EVIDENCE_ID, CONTROL_ID, USER_ID)]
    assert response.json()["reference"] == f"document_span:{EVIDENCE_ID}"


def test_existing_link_returns_200(client, monkeypatch):
    monkeypatch.setattr(f"{ENDPOINT}.link_evidence_to_control", lambda *args: (fake_link(), False))

    assert post_link(client).status_code == 200


@pytest.mark.parametrize(
    "error, expected",
    [
        (EvidenceNotFoundError("Evidence file not found."), 404),
        (ControlNotFoundError("Control not found."), 404),
        (EvidenceAssessmentMismatchError("Evidence file belongs to a different assessment."), 409),
    ],
)
def test_link_failures_map_to_status_codes(client, monkeypatch, error, expected):
    def failing(*args):
        raise error

    monkeypatch.setattr(f"{ENDPOINT}.link_evidence_to_control", failing)

    response = post_link(client)

    assert response.status_code == expected
    assert response.json()["detail"] == str(error)


def test_unlink_requires_membership(client, monkeypatch):
    monkeypatch.setattr(f"{ENDPOINT}.unlink_evidence_from_control", lambda *args: pytest.fail("must not be called"))

    response = client.delete(
        f"/api/v1/evidence/{EVIDENCE_ID}/controls/{CONTROL_ID}", params={"organization_id": str(uuid.uuid4())}
    )

    assert response.status_code == 403


@pytest.mark.parametrize("removed, expected", [(True, 204), (False, 404)])
def test_unlink_returns_204_or_404(client, monkeypatch, removed, expected):
    monkeypatch.setattr(f"{ENDPOINT}.unlink_evidence_from_control", lambda *args: removed)

    response = client.delete(
        f"/api/v1/evidence/{EVIDENCE_ID}/controls/{CONTROL_ID}", params={"organization_id": str(ORG_ID)}
    )

    assert response.status_code == expected


def test_list_by_control_uses_control_query_and_hides_extracted_text(client, monkeypatch):
    seen = []

    def fake_list_for_control(db, organization_id, assessment_control_id):
        seen.append((organization_id, assessment_control_id))
        return [
            SimpleNamespace(
                id=EVIDENCE_ID,
                organization_id=organization_id,
                assessment_id=ASSESSMENT_ID,
                uploaded_by_user_id=USER_ID,
                original_filename="policy.txt",
                content_type="text/plain",
                file_extension=".txt",
                size_bytes=23,
                sha256="a" * 64,
                created_at=datetime.now(timezone.utc),
                extracted_text="never exposed",
            )
        ]

    monkeypatch.setattr(f"{ENDPOINT}.list_evidence_for_control", fake_list_for_control)
    monkeypatch.setattr(f"{ENDPOINT}.list_evidence_files", lambda *args: pytest.fail("must not be called"))

    response = client.get(
        "/api/v1/evidence/", params={"organization_id": str(ORG_ID), "assessment_control_id": str(CONTROL_ID)}
    )

    assert response.status_code == 200
    assert seen == [(ORG_ID, CONTROL_ID)]
    assert [item["id"] for item in response.json()] == [str(EVIDENCE_ID)]
    assert "extracted_text" not in response.json()[0]


def test_document_reference_round_trip():
    assert evidence_file_id_from_reference(document_reference(EVIDENCE_ID)) == EVIDENCE_ID
    assert evidence_file_id_from_reference(document_reference(EVIDENCE_ID, page=4)) == EVIDENCE_ID
    assert document_reference(EVIDENCE_ID, page=4) == f"document_span:{EVIDENCE_ID}#page=4"


@pytest.mark.parametrize("reference", ["doc:1", "interview_turn:3", "document_span:not-a-uuid", ""])
def test_other_references_are_not_evidence_files(reference):
    assert evidence_file_id_from_reference(reference) is None
