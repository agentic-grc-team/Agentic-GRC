"""Review evidence resolution and organization/assessment isolation."""

from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.v1.dependencies import get_db_session
from app.db.models import EvidenceControlLink, OrganizationMembership
from app.main import app
from app.security.auth import get_current_user
from app.services.evidence_links import (
    document_reference,
    link_evidence_to_control,
    unlink_evidence_from_control,
)
from app.services.review_evidence import get_review_evidence
from tests.test_evidence_db import store
from tests.test_expert_review_db import (
    db,
    make_assessment,
    make_assessment_context,
    make_result,
    make_review_context,
    make_trace,
)


def make_evidence_result(db):
    org, user, assessment, control = make_assessment_context(db)

    document = store(
        db,
        org,
        assessment_id=assessment.id,
        original_filename="MFA-policy.txt",
    )

    linked_only = store(
        db,
        org,
        assessment_id=assessment.id,
        original_filename="new-attachment.txt",
    )

    link_evidence_to_control(
        db, org.id, document.id, control.id, user.id
    )
    link_evidence_to_control(
        db, org.id, linked_only.id, control.id, user.id
    )

    reference = document_reference(document.id, page=2)

    trace = make_trace(
        db,
        org,
        assessment,
        sources=[
            {
                "type": "document_span",
                "ref": reference,
                "excerpt": "MFA must be enabled.",
            },
            {
                "type": "interview_turn",
                "ref": "interview_turn:1",
                "excerpt": "Only admins use MFA.",
            },
        ],
    )

    result = make_result(
        db,
        org,
        control,
        trace_id=trace.id,
        evidence_pending=True,
        evidence_refs=[
            {
                "source_type": "document_span",
                "reference": reference,
                "excerpt": "MFA must be enabled.",
            },
        ],
    )

    return (
        org,
        user,
        assessment,
        control,
        result,
        document,
        linked_only,
    )


def test_resolves_citations_and_distinguishes_current_attachments(db):
    (
        org,
        user,
        assessment,
        control,
        result,
        document,
        linked_only,
    ) = make_evidence_result(db)

    evidence = get_review_evidence(db, result.id, user)

    assert evidence.evidence_pending is True
    assert len(evidence.sources) == 2
    assert evidence.sources[0].document.id == document.id
    assert evidence.sources[0].excerpt == "MFA must be enabled."
    assert evidence.sources[1].source_type == "interview_turn"

    assert {
        item.id for item in evidence.linked_documents
    } == {document.id, linked_only.id}

    payload = evidence.model_dump_json()

    assert "extracted_text" not in payload
    assert "stored_filename" not in payload


def test_unlinked_document_stays_a_historical_citation(db):
    (
        org,
        user,
        assessment,
        control,
        result,
        document,
        linked_only,
    ) = make_evidence_result(db)

    unlink_evidence_from_control(
        db, org.id, document.id, control.id
    )

    evidence = get_review_evidence(db, result.id, user)

    assert [
        item.id for item in evidence.linked_documents
    ] == [linked_only.id]

    assert evidence.sources[0].document.id == document.id


def test_foreign_document_citations_do_not_leak_data(db):
    org, user, assessment, control = make_assessment_context(db)

    other_assessment = make_assessment(db, org)

    other_document = store(
        db,
        org,
        assessment_id=other_assessment.id,
        original_filename="private-other-assessment.txt",
    )

    foreign_org, _, _, _, _, _ = make_review_context(db)

    foreign_document = store(
        db,
        foreign_org,
        original_filename="private-other-org.txt",
    )

    result = make_result(
        db,
        org,
        control,
        evidence_refs=[
            {
                "source_type": "document_span",
                "reference": document_reference(other_document.id),
                "excerpt": "secret A",
            },
            {
                "source_type": "document_span",
                "reference": document_reference(foreign_document.id),
                "excerpt": "secret B",
            },
            {
                "source_type": "document_span",
                "reference": document_reference(uuid4()),
                "excerpt": "missing file",
            },
            None,
        ],
    )

    evidence = get_review_evidence(db, result.id, user)

    assert len(evidence.sources) == 3

    assert all(
        source.document is None and source.excerpt is None
        for source in evidence.sources
    )

    assert evidence.skipped_source_count == 1
    assert evidence.linked_documents == []

    payload = evidence.model_dump_json()

    assert "secret" not in payload
    assert "private-" not in payload


def test_org_wide_document_can_be_cited(db):
    org, user, assessment, control = make_assessment_context(db)
    document = store(db, org)

    result = make_result(
        db,
        org,
        control,
        evidence_refs=[
            {
                "source_type": "document_span",
                "reference": document_reference(document.id),
            },
        ],
    )

    evidence = get_review_evidence(db, result.id, user)

    assert evidence.sources[0].document.id == document.id


def test_inconsistent_attachment_cannot_expose_another_assessment(db):
    org, user, assessment, control = make_assessment_context(db)
    other_assessment = make_assessment(db, org)

    document = store(
        db,
        org,
        assessment_id=other_assessment.id,
    )

    # Simulate a link inserted outside the normal service validation.
    db.add(
        EvidenceControlLink(
            organization_id=org.id,
            assessment_id=assessment.id,
            assessment_control_id=control.id,
            evidence_file_id=document.id,
        )
    )
    db.commit()

    result = make_result(
        db,
        org,
        control,
        evidence_refs=[],
    )

    evidence = get_review_evidence(db, result.id, user)

    assert evidence.linked_documents == []


def test_sources_from_a_different_control_trace_are_not_exposed(db):
    org, user, assessment, control = make_assessment_context(db)

    trace = make_trace(
        db,
        org,
        assessment,
        control_ids=["PR.AA-05"],
        sources=[
            {
                "type": "interview_turn",
                "ref": "interview_turn:private",
                "excerpt": "private statement",
            },
        ],
    )

    result = make_result(
        db,
        org,
        control,
        trace_id=trace.id,
        evidence_refs=[],
    )

    evidence = get_review_evidence(db, result.id, user)

    assert evidence.sources == []


@pytest.mark.parametrize(
    "role",
    ["representative", "foreign_consultant"],
)
def test_endpoint_denies_unauthorized_roles_and_tenants(
    db,
    monkeypatch,
    role,
):
    _, _, _, _, result, _ = make_review_context(db)

    if role == "representative":
        _, user, _, _, _, _ = make_review_context(
            db,
            role="representative",
        )

        db.add(
            OrganizationMembership(
                organization_id=result.organization_id,
                user_id=user.id,
                role="representative",
                status="active",
            )
        )
        db.commit()

        expected = 403
    else:
        _, user, _, _, _, _ = make_review_context(db)
        expected = 404

    monkeypatch.setitem(
        app.dependency_overrides,
        get_db_session,
        lambda: db,
    )

    monkeypatch.setitem(
        app.dependency_overrides,
        get_current_user,
        lambda: user,
    )

    response = TestClient(app).get(
        f"/api/v1/expert-reviews/{result.id}/evidence"
    )

    assert response.status_code == expected
    assert "sources" not in response.json()


def test_unknown_result_is_not_found(db):
    _, user, _, _, _, _ = make_review_context(db)

    with pytest.raises(HTTPException) as error:
        get_review_evidence(db, uuid4(), user)

    assert error.value.status_code == 404