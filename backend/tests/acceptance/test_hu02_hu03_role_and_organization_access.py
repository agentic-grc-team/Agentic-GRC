"""Acceptance tests for HU-02 and HU-03 — Organization isolation and role permissions (Jira AGRC-138).

HU-02: As a security officer at the assessed organization, I want my answers, documents, and findings
to be inaccessible from any other organization, so that I can use the tool with my company's sensitive
information.
HU-03: As a platform administrator, I want each user to have a role with distinct permissions, so that
the organization's representative can answer the interview without being able to alter findings or see
the agent's reasoning.

Each test is one acceptance criterion of AGRC-138, written as Given / When / Then. They run through the
HTTP API against PostgreSQL along the real flow: a consultant creates the assessment, a representative
answers the interview, uploads the evidence the agent asks for and answers again, and the agent saves a
draft result. Only the Supabase login is replaced by a fixed user and the language model by a
deterministic fake. Cross-organization cases for organizations, assessments, traces, reports, reviews
and evidence links are already in tests/test_cross_organization_api.py (AGRC-67); these tests add the
interview, interview evidence, gap list and role combinations. Results are recorded in
docs/testing/acceptance-tests.md.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agent.llm import FakeLLM
from app.agent.schemas import AnswerCategory, AnswerInterpretation, Intent, Specificity
from app.api.v1.dependencies import get_db_session
from app.db.models import (
    ControlResult,
    ControlResultReview,
    EvidenceControlLink,
    EvidenceFile,
    InterviewTurn,
    OrganizationMembership,
)
from app.main import app
from app.security.auth import get_current_user
from app.services.langgraph_checkpointer import open_interview_checkpointer
from tests.acceptance.test_hu25_inspect_reasoning_trace import db, member  # noqa: F401
from tests.test_assessments_db import make_organization, make_user

ANSWER = "Yes, MFA is enforced for all staff accounts, including cloud services."


@pytest.fixture
def api(db, monkeypatch, tmp_path):  # noqa: F811
    """HTTP client on the real app and database. `api.login(user)` sets who is calling.

    The fake model reads every answer as a detailed yes with scope, so the agent first asks for
    evidence and closes the control after the next answer.
    """
    fake_llm = FakeLLM(
        {
            "interpret_answer": lambda _user: AnswerInterpretation(
                intent=Intent.answer,
                category=AnswerCategory.yes,
                specificity=Specificity.detailed,
                mentions_scope=True,
                summary="MFA is enforced for all staff accounts.",
                rationale="The participant describes the control and its scope.",
                confidence=0.9,
                key_quote="MFA is enforced",
            )
        }
    )
    monkeypatch.setattr("app.agent.llm.OllamaLLM", lambda *_args, **_kwargs: fake_llm)
    monkeypatch.setattr("app.api.v1.endpoints.evidence.UPLOAD_DIR", str(tmp_path))
    monkeypatch.setitem(app.dependency_overrides, get_db_session, lambda: db)
    client = TestClient(app)
    client.thread_ids = []

    def login(user, platform_admin=False):
        signed_in = SimpleNamespace(id=user.id, email=user.email, is_platform_admin=platform_admin)
        monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: signed_in)

    client.login = login
    yield client
    if client.thread_ids:
        with open_interview_checkpointer() as checkpointer:
            for thread_id in client.thread_ids:
                checkpointer.delete_thread(str(thread_id))


def org_url(organization_id, suffix=""):
    return f"/api/v1/organizations/{organization_id}{suffix}"


def answer(api, interview_url, session_id, question_turn):
    response = api.post(
        f"{interview_url}/turns",
        json={
            "session_id": session_id,
            "content": ANSWER,
            "question_id": question_turn["question_id"],
            "replies_to_turn_id": question_turn["id"],
            "client_request_id": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def assessed_organization(db, api):  # noqa: F811
    """One organization taken through the flow up to a draft result waiting for expert review.

    The consultant creates the assessment; the representative opens the interview, answers, uploads
    the evidence the agent asks for and answers again, which closes the control as a draft.
    """
    organization = make_organization(db)
    consultant = member(db, organization, "consultant")
    representative = member(db, organization, "representative")

    api.login(consultant)
    created = api.post(org_url(organization.id, "/assessments"), json={"title": "Q4 identity review"})
    assert created.status_code == 201, created.text
    assessment_id = created.json()["id"]
    assessment_url = org_url(organization.id, f"/assessments/{assessment_id}")
    interview_url = f"{assessment_url}/interview"

    api.login(representative)
    opened = api.post(interview_url, json={"session_type": "kickoff"})
    assert opened.status_code == 201, opened.text
    session_id = opened.json()["session"]["id"]
    api.thread_ids.append(session_id)

    first = answer(api, interview_url, session_id, opened.json()["turns"][0])
    evidence_request = first["agent_turns"][-1]
    assert evidence_request["turn_type"] == "evidence_request"

    uploaded = api.post(
        "/api/v1/evidence/",
        data={
            "organization_id": str(organization.id),
            "assessment_id": assessment_id,
            "interview_session_id": session_id,
            "evidence_request_turn_id": evidence_request["id"],
        },
        files={"file": ("mfa-policy.txt", b"MFA is required for every staff account.", "text/plain")},
    )
    assert uploaded.status_code == 200, uploaded.text

    second = answer(api, interview_url, session_id, evidence_request)
    assert second["draft_results"], second

    api.login(consultant)
    pending = api.get("/api/v1/expert-reviews/pending")
    assert pending.status_code == 200, pending.text
    (item,) = [entry for entry in pending.json() if entry["assessment_id"] == assessment_id]

    return SimpleNamespace(
        organization=organization,
        consultant=consultant,
        representative=representative,
        assessment_id=assessment_id,
        assessment_url=assessment_url,
        interview_url=interview_url,
        session_id=session_id,
        evidence_request=evidence_request,
        evidence_id=uploaded.json()["id"],
        result_id=item["result_id"],
    )


def review_url(result_id, suffix=""):
    return f"/api/v1/expert-reviews/{result_id}{suffix}"


ACCEPT = {"outcome": "accepted", "comment": "Policy and configuration checked."}


def test_access_ac1_consultant_reviews_in_own_organization(db, api):  # noqa: F811
    """AC 1
    Given a consultant with an active membership in the organization,
    when a draft result of that organization waits for review,
    then the consultant sees it in the queue, opens its trace and evidence, and records a decision.
    """
    org = assessed_organization(db, api)
    api.login(org.consultant)

    pending = api.get("/api/v1/expert-reviews/pending").json()
    assert org.result_id in {item["result_id"] for item in pending}

    trace = api.get(review_url(org.result_id, "/trace"))
    assert trace.status_code == 200, trace.text
    assert trace.json()["organization_id"] == str(org.organization.id)

    evidence = api.get(review_url(org.result_id, "/evidence"))
    assert evidence.status_code == 200, evidence.text

    traces = api.get(f"{org.assessment_url}/traces")
    assert traces.status_code == 200, traces.text
    assert traces.json()

    decision = api.post(review_url(org.result_id, "/decision"), json=ACCEPT)
    assert decision.status_code == 200, decision.text
    assert decision.json()["outcome"] == "accepted"


def test_access_ac2_representative_answers_and_provides_evidence_but_cannot_review(db, api):  # noqa: F811
    """AC 2
    Given a representative with an active membership in the organization,
    when they answer the interview and upload the evidence the agent asks for,
    then the answers and the evidence are saved for that organization,
    and the representative cannot see the review queue, record a decision, or inspect reasoning traces.
    """
    org = assessed_organization(db, api)

    # The interview answers and the evidence were saved by the representative, for this organization.
    participant_turns = db.scalars(
        select(InterviewTurn).where(
            InterviewTurn.session_id == uuid.UUID(org.session_id),
            InterviewTurn.speaker == "participant",
        )
    ).all()
    assert len(participant_turns) == 2
    evidence = db.get(EvidenceFile, uuid.UUID(org.evidence_id))
    assert evidence.organization_id == org.organization.id
    assert evidence.uploaded_by_user_id == org.representative.id
    links = db.scalars(
        select(EvidenceControlLink).where(EvidenceControlLink.evidence_file_id == evidence.id)
    ).all()
    assert len(links) == 1

    api.login(org.representative)
    assert api.get(org.interview_url, params={"session_id": org.session_id}).status_code == 200
    files = api.get("/api/v1/evidence/", params={"organization_id": str(org.organization.id)})
    assert files.status_code == 200, files.text
    assert org.evidence_id in {item["id"] for item in files.json()}

    # No expert review and no reasoning traces for the representative.
    assert org.result_id not in {item["result_id"] for item in api.get("/api/v1/expert-reviews/pending").json()}
    assert api.post(review_url(org.result_id, "/decision"), json=ACCEPT).status_code == 403
    assert api.get(review_url(org.result_id, "/trace")).status_code == 403
    assert api.get(review_url(org.result_id, "/evidence")).status_code == 403
    assert api.get(f"{org.assessment_url}/traces").status_code == 403
    assert api.get(f"{org.assessment_url}/traces/export").status_code == 403

    # The draft is unchanged: still version 1 by the agent, with no review recorded.
    result = db.get(ControlResult, uuid.UUID(org.result_id))
    assert result.version_no == 1
    assert result.author_actor == "agent"
    assert db.query(ControlResultReview).filter_by(control_result_id=result.id).count() == 0


@pytest.mark.parametrize("role", ["consultant", "representative"])
def test_access_ac3_no_role_reaches_another_organization(db, api, role):  # noqa: F811
    """AC 3
    Given two organizations, each with an assessment, interview, evidence and draft result,
    when a consultant or a representative of organization A uses organization B's identifiers,
    then every interview, evidence, finding, gap list and report request fails with no data,
    and nothing is written to organization B.
    """
    org_a = assessed_organization(db, api)
    org_b = assessed_organization(db, api)
    turns_before = db.query(InterviewTurn).filter_by(session_id=uuid.UUID(org_b.session_id)).count()
    api.login(getattr(org_a, role))

    # Interview of B, through B's path and through A's path with B's assessment.
    for url in (org_b.interview_url, org_url(org_a.organization.id, f"/assessments/{org_b.assessment_id}/interview")):
        assert api.get(url, params={"session_id": org_b.session_id}).status_code == 404
        assert api.get(f"{url}/status").status_code == 404
        assert api.post(url, json={"session_type": "kickoff"}).status_code == 404
        reply = api.post(
            f"{url}/turns",
            json={
                "session_id": org_b.session_id,
                "content": "Injected answer.",
                "question_id": org_b.evidence_request["question_id"],
                "replies_to_turn_id": org_b.evidence_request["id"],
                "client_request_id": str(uuid.uuid4()),
            },
        )
        assert reply.status_code == 404

    # Evidence of B: list, upload into B's interview, and links.
    b_org_id = str(org_b.organization.id)
    assert api.get("/api/v1/evidence/", params={"organization_id": b_org_id}).status_code == 403
    assert api.get(
        "/api/v1/evidence/links", params={"organization_id": b_org_id, "assessment_id": org_b.assessment_id}
    ).status_code == 403
    upload = api.post(
        "/api/v1/evidence/",
        data={
            "organization_id": b_org_id,
            "assessment_id": org_b.assessment_id,
            "interview_session_id": org_b.session_id,
            "evidence_request_turn_id": org_b.evidence_request["id"],
        },
        files={"file": ("other.txt", b"Not yours.", "text/plain")},
    )
    assert upload.status_code == 403

    # Findings of B: review queue, decision, trace and evidence of B's draft.
    assert org_b.result_id not in {item["result_id"] for item in api.get("/api/v1/expert-reviews/pending").json()}
    assert api.post(review_url(org_b.result_id, "/decision"), json=ACCEPT).status_code == 404
    assert api.get(review_url(org_b.result_id, "/trace")).status_code == 404
    assert api.get(review_url(org_b.result_id, "/evidence")).status_code == 404

    # Gap list and report of B, through B's path and through A's path with B's assessment.
    for base in (org_b.assessment_url, org_url(org_a.organization.id, f"/assessments/{org_b.assessment_id}")):
        for suffix in ("/gaps", "/report", "/report.pdf"):
            assert api.get(f"{base}{suffix}").status_code == 404, f"{base}{suffix}"

    # Nothing was written to B.
    assert db.query(InterviewTurn).filter_by(session_id=uuid.UUID(org_b.session_id)).count() == turns_before
    assert db.query(EvidenceFile).filter_by(organization_id=org_b.organization.id).count() == 1
    assert db.query(ControlResultReview).filter_by(control_result_id=uuid.UUID(org_b.result_id)).count() == 0


def test_access_ac4_report_and_gap_list_only_for_members_of_the_organization(db, api):  # noqa: F811
    """AC 4
    Given an assessment whose draft the consultant has accepted,
    when the report and the gap list are requested,
    then the organization's consultant and representative get them,
    and a member of another organization, a suspended member and a user with no membership get no data.
    """
    org = assessed_organization(db, api)
    other = assessed_organization(db, api)
    api.login(org.consultant)
    assert api.post(review_url(org.result_id, "/decision"), json=ACCEPT).status_code == 200

    suspended = member(db, org.organization, "consultant", status="suspended")
    outsider = make_user(db)

    for user in (org.consultant, org.representative):
        api.login(user)
        report = api.get(f"{org.assessment_url}/report")
        assert report.status_code == 200, report.text
        assert report.json()["assessment"]["id"] == org.assessment_id
        pdf = api.get(f"{org.assessment_url}/report.pdf")
        assert pdf.status_code == 200
        assert pdf.content.startswith(b"%PDF")
        gaps = api.get(f"{org.assessment_url}/gaps")
        assert gaps.status_code == 200, gaps.text
        assert gaps.json()["assessment_id"] == org.assessment_id

    for user in (other.consultant, other.representative, suspended, outsider):
        api.login(user)
        for suffix in ("/report", "/report.pdf", "/gaps"):
            assert api.get(f"{org.assessment_url}{suffix}").status_code == 404, suffix

    # The suspended membership really exists for this organization, so the 404 comes from its status.
    assert db.scalar(
        select(OrganizationMembership.status).where(
            OrganizationMembership.organization_id == org.organization.id,
            OrganizationMembership.user_id == suspended.id,
        )
    ) == "suspended"
