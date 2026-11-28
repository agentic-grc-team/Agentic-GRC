"""Acceptance tests for HU-12 — Identify document passages relevant to controls (Jira AGRC-128).

HU-12: As an Aligo consultant, I want the agent to identify which parts of an uploaded document
relate to which controls, so that I can review the supporting passages without reading the entire
document.

Each test is one acceptance criterion of AGRC-128, written as Given / When / Then. They run through
the HTTP API against PostgreSQL: a consultant creates the assessment, so its NIST controls come from
the knowledge base, and the documents are uploaded through the evidence endpoint, so the text is
extracted from a real PDF with its page breaks. Only the Supabase login is replaced by a fixed user.
The unit and API tests of the matcher are in tests/test_passage_matching.py and
tests/test_passage_matching_api.py; these tests check the criteria end to end. Results are recorded
in docs/testing/acceptance-tests.md.
"""

import io
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from sqlalchemy import func, select

from app.api.v1.dependencies import get_db_session
from app.db.models import ControlResult, EvidenceControlLink, EvidenceFile
from app.main import app
from app.security.auth import get_current_user
from tests.acceptance.test_hu25_inspect_reasoning_trace import db, member  # noqa: F401
from tests.test_assessments_db import make_organization

MFA_SENTENCE = "All administrator accounts must use multi-factor authentication with an authenticator app."


def policy_pdf() -> bytes:
    """A two-page policy: a cover page, then an MFA section and an unrelated facilities section."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 760, "Halverston Community Bank")
    pdf.drawString(72, 740, "Information Security Policy Handbook")
    pdf.showPage()
    lines = [
        "3. PRIVILEGED ACCESS",
        "All administrator accounts must use multi-factor authentication",
        "with an authenticator app.",
        "4. FACILITIES",
        "The cafeteria opens at eight and closes at six.",
        "The facilities administrator keeps the visitor log at the front desk.",
    ]
    for number, line in enumerate(lines):
        pdf.drawString(72, 760 - 20 * number, line)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


@pytest.fixture
def api(db, monkeypatch, tmp_path):  # noqa: F811
    """HTTP client on the real app and database. `api.login(user)` sets who is calling."""
    monkeypatch.setattr("app.api.v1.endpoints.evidence.UPLOAD_DIR", str(tmp_path))
    monkeypatch.setitem(app.dependency_overrides, get_db_session, lambda: db)
    client = TestClient(app)

    def login(user):
        signed_in = SimpleNamespace(id=user.id, email=user.email, is_platform_admin=False)
        monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: signed_in)

    client.login = login
    return client


def matches_url(organization_id, assessment_id):
    return f"/api/v1/organizations/{organization_id}/assessments/{assessment_id}/passage-matches"


def create_assessment(api, organization_id, title):
    created = api.post(f"/api/v1/organizations/{organization_id}/assessments", json={"title": title})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def upload(api, organization_id, assessment_id, name, content, content_type):
    """Upload through the evidence endpoint; without an assessment id the file is shared by the organization."""
    data = {"organization_id": str(organization_id)}
    if assessment_id is not None:
        data["assessment_id"] = assessment_id
    uploaded = api.post("/api/v1/evidence/", data=data, files={"file": (name, content, content_type)})
    assert uploaded.status_code == 200, uploaded.text
    return uploaded.json()["id"]


def organization_with_documents(db, api):  # noqa: F811
    """An organization whose representative uploaded a policy PDF and an unrelated note."""
    organization = make_organization(db)
    consultant = member(db, organization, "consultant")
    representative = member(db, organization, "representative")

    api.login(consultant)
    assessment_id = create_assessment(api, organization.id, "Q4 identity review")

    api.login(representative)
    policy_id = upload(api, organization.id, assessment_id, "access-policy.pdf", policy_pdf(), "application/pdf")
    note_id = upload(
        api, organization.id, assessment_id, "cafeteria.txt", b"The cafeteria opens at eight.", "text/plain"
    )
    return SimpleNamespace(
        organization=organization,
        consultant=consultant,
        representative=representative,
        assessment_id=assessment_id,
        url=matches_url(organization.id, assessment_id),
        policy_id=policy_id,
        note_id=note_id,
    )


def get_matches(api, url, **params):
    response = api.get(url, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_hu12_ac1_relevant_passage_matched_to_control_with_file_and_page(db, api):  # noqa: F811
    """AC 1
    Given an uploaded PDF whose second page has a section on multi-factor authentication,
    when the consultant asks for the assessment's passage matches,
    then that passage is matched to PR.AA-03 with the file, the page and the section,
    and the location points at exactly that passage in the extracted text.
    """
    org = organization_with_documents(db, api)
    api.login(org.consultant)

    body = get_matches(api, org.url)
    [match] = [item for item in body["matches"] if item["evidence_file_id"] == org.policy_id]

    assert match["control_code"] == "PR.AA-03"
    assert match["file_name"] == "access-policy.pdf"
    assert match["locator"]["page"] == 2
    assert match["locator"]["section"] == "3. PRIVILEGED ACCESS"
    assert match["reference"] == f"document_span:{org.policy_id}#page=2"
    assert match["excerpt"] == MFA_SENTENCE
    assert "multi factor authentication" in match["matched_terms"]

    extracted = db.get(EvidenceFile, uuid.UUID(org.policy_id)).extracted_text
    start, end = match["locator"]["char_start"], match["locator"]["char_end"]
    assert " ".join(extracted[start:end].split()) == MFA_SENTENCE


def test_hu12_ac2_unrelated_passage_is_not_supporting_evidence(db, api):  # noqa: F811
    """AC 2
    Given the same PDF with a facilities section, and an uploaded note about the cafeteria,
    when the consultant asks for the passage matches,
    then no passage of the facilities section and nothing from the note is proposed for any control,
    even though the facilities section uses the word "administrator".
    """
    org = organization_with_documents(db, api)
    api.login(org.consultant)

    body = get_matches(api, org.url)

    assert body["files_checked"] == 2
    assert all(item["evidence_file_id"] != org.note_id for item in body["matches"])
    assert all(item["locator"]["section"] != "4. FACILITIES" for item in body["matches"])
    assert all("cafeteria" not in item["excerpt"] for item in body["matches"])
    assert all("visitor log" not in item["excerpt"] for item in body["matches"])
    assert len(body["matches"]) == 1


def test_hu12_ac3_matches_stay_in_their_organization_and_assessment(db, api):  # noqa: F811
    """AC 3
    Given organization A with the policy in one assessment and a copy shared by the whole
    organization, a second assessment of A, and an organization B,
    when a member of B, or the second assessment of A, asks for matches of A's documents,
    then B gets 404 for A's assessment through both URL paths, B's own assessment gets no match from
    A's files even when their ids are given, and A's second assessment does not reuse the match of
    the first assessment's file; it only gets the shared copy.
    """
    org_a = organization_with_documents(db, api)
    api.login(org_a.consultant)
    second_assessment = create_assessment(api, org_a.organization.id, "Q1 follow-up")
    # A copy shared by the whole organization (no assessment): every assessment of A may use it.
    shared_id = upload(api, org_a.organization.id, None, "shared-policy.pdf", policy_pdf(), "application/pdf")

    org_b = make_organization(db)
    outsider = member(db, org_b, "consultant")
    api.login(outsider)
    own_assessment = create_assessment(api, org_b.id, "B baseline")

    # B cannot read A's matches, neither through A's path nor through its own path.
    assert api.get(org_a.url).status_code == 404
    assert api.get(matches_url(org_b.id, org_a.assessment_id)).status_code == 404

    # B's own assessment does not pick up A's files, even when asked for them by id.
    for file_id in (org_a.policy_id, shared_id):
        foreign = get_matches(api, matches_url(org_b.id, own_assessment), evidence_file_id=file_id)
        assert foreign["files_checked"] == 0
        assert foreign["matches"] == []
    assert get_matches(api, matches_url(org_b.id, own_assessment))["files_checked"] == 0

    # Inside A, the first file belongs to the first assessment only, so the second one does not reuse
    # it; the shared copy is matched for the second assessment, with its own file id.
    api.login(org_a.consultant)
    second_url = matches_url(org_a.organization.id, second_assessment)
    assert get_matches(api, second_url, evidence_file_id=org_a.policy_id)["matches"] == []
    [shared] = get_matches(api, second_url)["matches"]
    assert shared["evidence_file_id"] == shared_id
    assert shared["assessment_id"] == second_assessment

    # Any role of A can read A's matches: the representative uploaded the documents.
    api.login(org_a.representative)
    assert {item["evidence_file_id"] for item in get_matches(api, org_a.url)["matches"]} == {
        org_a.policy_id,
        shared_id,
    }


def test_hu12_ac4_reprocessing_creates_no_duplicates(db, api):  # noqa: F811
    """AC 4
    Given the uploaded documents,
    when the matches are requested again, for the whole assessment and for the policy file alone,
    then every request returns the same single match, with no duplicate passage,
    and nothing is written: no evidence link and no control result is created.
    """
    org = organization_with_documents(db, api)
    api.login(org.consultant)

    def written():
        links = db.scalar(
            select(func.count()).select_from(EvidenceControlLink).where(
                EvidenceControlLink.organization_id == org.organization.id
            )
        )
        results = db.scalar(
            select(func.count()).select_from(ControlResult).where(
                ControlResult.organization_id == org.organization.id
            )
        )
        return links, results

    before = written()
    first = get_matches(api, org.url)["matches"]
    second = get_matches(api, org.url)["matches"]
    only_policy = get_matches(api, org.url, evidence_file_id=org.policy_id)["matches"]

    assert first == second == only_policy
    keys = [(item["evidence_file_id"], item["control_code"], item["locator"]["char_start"]) for item in first]
    assert len(keys) == len(set(keys)) == 1
    assert written() == before == (0, 0)


def test_hu12_ac5_proposed_matches_remain_unverified(db, api):  # noqa: F811
    """AC 5
    Given a proposed match of the policy to PR.AA-03,
    when it is read, and again after the consultant links the file to PR.AA-03,
    then the match is marked not verified both times, only `linked` changes,
    and the control still has no result.
    """
    org = organization_with_documents(db, api)
    api.login(org.consultant)

    [before] = get_matches(api, org.url)["matches"]
    assert before["verification"] == "not_verified"
    assert before["linked"] is False

    linked = api.post(
        f"/api/v1/evidence/{org.policy_id}/controls",
        json={
            "organization_id": str(org.organization.id),
            "assessment_control_id": before["assessment_control_id"],
        },
    )
    assert linked.status_code == 201, linked.text

    [after] = get_matches(api, org.url)["matches"]
    assert after["verification"] == "not_verified"
    assert after["linked"] is True
    assert {key: value for key, value in after.items() if key != "linked"} == {
        key: value for key, value in before.items() if key != "linked"
    }
    assert (
        db.scalar(
            select(func.count()).select_from(ControlResult).where(
                ControlResult.assessment_control_id == uuid.UUID(before["assessment_control_id"])
            )
        )
        == 0
    )
