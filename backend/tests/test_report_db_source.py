"""Integration tests for DbReportSource using a real PostgreSQL database."""

import logging
import uuid
from datetime import datetime, timezone
from io import BytesIO

import pdfplumber
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import (
    Assessment,
    AssessmentControl,
    ControlResult,
    ControlResultReview,
    DecisionTraceRecord,
    EvidenceControlLink,
    EvidenceFile,
    Organization,
    User,
)
from app.db.session import get_engine
from app.schemas.assessments import AssessmentCreate
from app.services.assessment_scope import controls_for_kb_version
from app.services.assessments import start_assessment
from app.services.reports.builder import build_report_view
from app.services.reports.pdf import render_report_pdf
from app.services.reports.source import DbReportSource
from scripts.seed_demo_assessment import seed_demo_assessment_data


@pytest.fixture
def db():
    """A session inside a transaction that is rolled back after each test, so nothing is left behind."""
    try:
        engine = get_engine()
        connection = engine.connect()
    except (OSError, SQLAlchemyError, RuntimeError):
        pytest.skip("PostgreSQL is unavailable for integration tests.")
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()


def make_organization(db: Session) -> Organization:
    organization = Organization(
        name=f"Test org {uuid.uuid4()}", sector_code="other", size_code="unknown"
    )
    db.add(organization)
    db.commit()
    return organization


def make_user(db: Session) -> User:
    """A consultant profile. Every profile needs a Supabase auth.users row (stubbed in CI)."""
    user_id = uuid.uuid4()
    email = f"consultant-{user_id}@example.com"
    now = datetime.now(timezone.utc)
    db.execute(
        text(
            "INSERT INTO auth.users (id, aud, role, email, encrypted_password, email_confirmed_at, "
            "raw_app_meta_data, raw_user_meta_data, created_at, updated_at) "
            "VALUES (:id, 'authenticated', 'authenticated', :email, '', :now, '{}'::jsonb, '{}'::jsonb, :now, :now)"
        ),
        {"id": user_id, "email": email, "now": now},
    )
    user = User(id=user_id, email=email)
    db.add(user)
    db.commit()
    return user


def make_assessment(db: Session, organization: Organization, **changes) -> Assessment:
    fields = {
        "organization_id": organization.id,
        "title": f"Test assessment {uuid.uuid4()}",
        "framework_code": "NIST-CSF",
        "framework_version": "2.0",
        "kb_version": "demo-0.2",
        "status": "in_progress",
        "started_at": datetime.now(timezone.utc),
    }
    fields.update(changes)
    assessment = Assessment(**fields)
    db.add(assessment)
    db.commit()
    return assessment


def make_control(
    db: Session, organization: Organization, assessment: Assessment, **changes
) -> AssessmentControl:
    fields = {
        "organization_id": organization.id,
        "assessment_id": assessment.id,
        "control_code": "PR.AA-03",
        "control_title": "Identities and credentials are managed",
        "in_scope": True,
        "scope_rationale": None,
    }
    fields.update(changes)
    control = AssessmentControl(**fields)
    db.add(control)
    db.commit()
    return control


def make_result(
    db: Session, organization: Organization, control: AssessmentControl, **changes
) -> ControlResult:
    fields = {
        "organization_id": organization.id,
        "assessment_id": control.assessment_id,
        "assessment_control_id": control.id,
        "version_no": 1,
        "based_on_result_id": None,
        "author_actor": "agent",
        "author_user_id": None,
        "control_status": "partially_implemented",
        "explanation": "MFA is partially implemented across systems.",
        "confidence": 0.8,
        "requires_human_review": False,
        "evidence_pending": False,
        "evidence_summary": "Some systems enforce MFA, others do not.",
        "evidence_refs": [
            {
                "source_type": "document_span",
                "reference": "doc:1",
                "excerpt": "MFA used",
                "nature": "implementation",
            }
        ],
    }
    fields.update(changes)
    result = ControlResult(**fields)
    db.add(result)
    db.commit()
    return result


def make_trace(
    db: Session, organization: Organization, assessment: Assessment, **changes
) -> DecisionTraceRecord:
    fields = {
        "organization_id": organization.id,
        "assessment_id": assessment.id,
        "decision_type": "status_assessed",
        "control_ids": ["PR.AA-03"],
        "module": "Access",
        "sources": [
            {
                "type": "interview_turn",
                "ref": "interview_turn:1",
                "excerpt": "No MFA for admins.",
            }
        ],
        "actor_type": "agent",
        "prompt_id": "rule:close-on-no",
        "prompt_version": "0.1.0",
        "kb_version": "csf2.0-kb-0.1",
        "output": {"status": "not_implemented"},
        "rationale": "The participant said MFA is not enforced for admins.",
        "confidence": 0.85,
    }
    fields.update(changes)
    trace = DecisionTraceRecord(**fields)
    db.add(trace)
    db.commit()
    return trace


def make_review(
    db: Session,
    organization: Organization,
    result: ControlResult,
    user: User,
    **changes,
) -> ControlResultReview:
    fields = {
        "organization_id": organization.id,
        "assessment_id": result.assessment_id,
        "control_result_id": result.id,
        "outcome": "accepted",
        "resulting_result_id": None,
        "comment": "Accepted by reviewer.",
        "reviewed_by_user_id": user.id,
        "review_trace_id": None,
    }
    fields.update(changes)
    review = ControlResultReview(**fields)
    db.add(review)
    db.commit()
    return review


def test_report_db_source_table_mapping(db):
    """Test 1: 7-control set status, basis, reasons, exclusion, and scope filtering."""
    org = make_organization(db)
    user_a = make_user(db)
    assess = make_assessment(db, org)

    # 1. PR.AA-01: agent v1 implemented + review accepted by user A
    c_aa01 = make_control(
        db,
        org,
        assess,
        control_code="PR.AA-01",
        control_title="Identities and credentials",
        in_scope=True,
    )
    r_aa01 = make_result(
        db,
        org,
        c_aa01,
        version_no=1,
        author_actor="agent",
        author_user_id=None,
        control_status="implemented",
        explanation="Identities managed centrally.",
    )
    make_review(
        db,
        org,
        r_aa01,
        user_a,
        outcome="accepted",
        comment="Confirmed by user A.",
    )

    # 2. PR.AA-03: agent v1 + review modified (resulting v2) + consultant v2 partially_implemented by user A
    c_aa03 = make_control(
        db,
        org,
        assess,
        control_code="PR.AA-03",
        control_title="Users authenticated",
        in_scope=True,
    )
    r_aa03_v1 = make_result(
        db,
        org,
        c_aa03,
        version_no=1,
        author_actor="agent",
        author_user_id=None,
        control_status="implemented",
        explanation="Agent proposal.",
    )
    r_aa03_v2 = make_result(
        db,
        org,
        c_aa03,
        version_no=2,
        based_on_result_id=r_aa03_v1.id,
        author_actor="aligo_consultant",
        author_user_id=user_a.id,
        control_status="partially_implemented",
        explanation="Consultant modified: MFA partial.",
    )
    make_review(
        db,
        org,
        r_aa03_v1,
        user_a,
        outcome="modified",
        resulting_result_id=r_aa03_v2.id,
        comment="Modified to partially implemented.",
    )

    # 3. PR.AA-05: agent v1 implemented, evidence_pending=True, no review
    c_aa05 = make_control(
        db,
        org,
        assess,
        control_code="PR.AA-05",
        control_title="Access permissions defined",
        in_scope=True,
    )
    make_result(
        db,
        org,
        c_aa05,
        version_no=1,
        author_actor="agent",
        author_user_id=None,
        control_status="implemented",
        explanation="Access managed.",
        evidence_pending=True,
    )

    # 4. ID.AM-01: agent v1 not_implemented + review rejected
    c_am01 = make_control(
        db,
        org,
        assess,
        control_code="ID.AM-01",
        control_title="Inventories maintained",
        in_scope=True,
    )
    r_am01 = make_result(
        db,
        org,
        c_am01,
        version_no=1,
        author_actor="agent",
        author_user_id=None,
        control_status="not_implemented",
        explanation="No inventory.",
    )
    make_review(
        db,
        org,
        r_am01,
        user_a,
        outcome="rejected",
        comment="Rejected: inventory exists.",
    )

    # 5. PR.PS-06: consultant v1 not_applicable with justification
    c_ps06 = make_control(
        db,
        org,
        assess,
        control_code="PR.PS-06",
        control_title="Secure software development",
        in_scope=True,
    )
    make_result(
        db,
        org,
        c_ps06,
        version_no=1,
        author_actor="aligo_consultant",
        author_user_id=user_a.id,
        control_status="not_applicable",
        explanation="No internal dev.",
        justification="Organization does not develop software in-house.",
    )

    # 6. DE.CM-01: in_scope=True, no results
    make_control(
        db,
        org,
        assess,
        control_code="DE.CM-01",
        control_title="Network monitoring",
        in_scope=True,
    )

    # 7. GV.OC-01: in_scope=False with rationale
    make_control(
        db,
        org,
        assess,
        control_code="GV.OC-01",
        control_title="Organizational context",
        in_scope=False,
        scope_rationale="Out of scope for this assessment.",
    )

    source = DbReportSource()
    report_input = source.load(db, org.id, assess.id)
    assert report_input is not None
    assert report_input.is_demo_data is False

    # Check input controls: only in-scope controls, sorted by control_code
    input_control_codes = [c.code for c in report_input.controls]
    assert input_control_codes == [
        "DE.CM-01",
        "ID.AM-01",
        "PR.AA-01",
        "PR.AA-03",
        "PR.AA-05",
        "PR.PS-06",
    ]
    assert "GV.OC-01" not in input_control_codes

    view = build_report_view(report_input, datetime.now(timezone.utc))
    assert view.is_demo_data is False

    # Check scope list does not contain GV.OC-01
    scope_codes = [s.code for s in view.scope]
    assert scope_codes == [
        "DE.CM-01",
        "ID.AM-01",
        "PR.AA-01",
        "PR.AA-03",
        "PR.AA-05",
        "PR.PS-06",
    ]
    assert "GV.OC-01" not in scope_codes

    # Check results
    res_aa01 = next(r for r in view.results if r.code == "PR.AA-01")
    assert res_aa01.basis == "accepted_agent_result"
    assert res_aa01.reviewed_by == "Aligo consultant"
    assert res_aa01.control_status == "implemented"

    res_aa03 = next(r for r in view.results if r.code == "PR.AA-03")
    assert res_aa03.basis == "consultant_version"
    assert res_aa03.reviewed_by == "Aligo consultant"
    assert res_aa03.control_status == "partially_implemented"

    # Check pending
    pending_aa05 = next(p for p in view.pending if p.code == "PR.AA-05")
    assert pending_aa05.reason == "awaiting_review"

    pending_am01 = next(p for p in view.pending if p.code == "ID.AM-01")
    assert pending_am01.reason == "rejected_awaiting_new_version"

    pending_cm01 = next(p for p in view.pending if p.code == "DE.CM-01")
    assert pending_cm01.reason == "no_result"

    # Check exclusions
    ex_ps06 = next(e for e in view.exclusions if e.code == "PR.PS-06")
    assert ex_ps06.justification == "Organization does not develop software in-house."
    assert ex_ps06.reviewed_by == "Aligo consultant"

    # Check GV.OC-01 is not anywhere in the report
    all_report_codes = (
        [r.code for r in view.results]
        + [p.code for p in view.pending]
        + [e.code for e in view.exclusions]
    )
    assert "GV.OC-01" not in all_report_codes


def test_evidence_refs_parsing_limits_and_skipping(db, caplog):
    """Test 2: evidence parsing, 400 chars excerpt truncation to 300, invalid item skipped."""
    org = make_organization(db)
    user_a = make_user(db)
    assess = make_assessment(db, org)
    control = make_control(
        db,
        org,
        assess,
        control_code="PR.AA-01",
        control_title="Identities and credentials",
        in_scope=True,
    )

    long_excerpt = "E" * 400
    expected_truncated = "E" * 297 + "..."
    assert len(expected_truncated) == 300

    evidence_refs = [
        {
            "source_type": "document_span",
            "reference": "Policy.pdf, p. 4",
            "excerpt": "Valid excerpt text.",
            "nature": "intent",
        },
        {
            "source_type": "tenant_configuration",
            "reference": "Azure AD Config",
            "excerpt": long_excerpt,
            "nature": "implementation",
        },
        {
            "source_type": "invalid_source_type",
            "reference": "Unknown source",
            "nature": "intent",
        },
        {
            "source_type": "document_span",
            "reference": "Missing nature",
        },
        "not_a_dictionary",
    ]

    result = make_result(
        db,
        org,
        control,
        version_no=1,
        author_actor="agent",
        author_user_id=None,
        control_status="implemented",
        explanation="Test explanation.",
        evidence_refs=evidence_refs,
    )
    make_review(db, org, result, user_a, outcome="accepted")

    source = DbReportSource()
    with caplog.at_level(logging.WARNING, logger="app.services.reports.source"):
        report_input = source.load(db, org.id, assess.id)
    assert report_input is not None

    # One warning per skipped item, naming the result but never the evidence text.
    warnings = [record.getMessage() for record in caplog.records]
    assert len(warnings) == 3
    assert all(str(result.id) in message for message in warnings)
    assert "Unknown source" not in caplog.text
    assert "Missing nature" not in caplog.text
    assert "not_a_dictionary" not in caplog.text

    version = report_input.controls[0].versions[0]
    assert len(version.evidence) == 2

    ev1 = version.evidence[0]
    assert ev1.source_type == "document_span"
    assert ev1.reference == "Policy.pdf, p. 4"
    assert ev1.excerpt == "Valid excerpt text."
    assert ev1.nature == "intent"

    ev2 = version.evidence[1]
    assert ev2.source_type == "tenant_configuration"
    assert ev2.reference == "Azure AD Config"
    assert ev2.excerpt == expected_truncated
    assert len(ev2.excerpt) == 300
    assert ev2.nature == "implementation"

    view = build_report_view(report_input, datetime.now(timezone.utc))
    assert len(view.results) == 1
    assert len(view.results[0].evidence) == 2


def test_wrong_organization_returns_none(db):
    """Test 3: assessment of organization A requested with organization B's id -> None."""
    org_a = make_organization(db)
    org_b = make_organization(db)
    assess = make_assessment(db, org_a)

    source = DbReportSource()
    assert source.load(db, org_b.id, assess.id) is None
    # The same id with its own organization is found, so the None above comes from the organization filter.
    assert source.load(db, org_a.id, assess.id) is not None


def test_unknown_assessment_id_returns_none(db):
    """Test 4: unknown assessment id -> None."""
    org = make_organization(db)
    # The organization has an assessment, so a source that ignored the assessment id would return it.
    existing = make_assessment(db, org)
    source = DbReportSource()
    assert source.load(db, org.id, uuid.uuid4()) is None
    assert source.load(db, org.id, existing.id) is not None


def test_framework_label_formatting(db):
    """Test 5: framework_code='NIST-CSF', framework_version='2.0' -> 'NIST CSF 2.0'."""
    org = make_organization(db)
    assess_csf = make_assessment(
        db, org, framework_code="NIST-CSF", framework_version="2.0"
    )
    source = DbReportSource()
    res_csf = source.load(db, org.id, assess_csf.id)
    assert res_csf is not None
    assert res_csf.assessment.framework == "NIST CSF 2.0"

    assess_other = make_assessment(
        db, org, framework_code="ISO-27001", framework_version="2022"
    )
    res_other = source.load(db, org.id, assess_other.id)
    assert res_other is not None
    assert res_other.assessment.framework == "ISO-27001 2022"


def test_accepted_agent_result_with_evidence_pending(db):
    """Test 6: accepted agent result with evidence_pending=True -> final and counted in summary."""
    org = make_organization(db)
    user_a = make_user(db)
    assess = make_assessment(db, org)
    control = make_control(
        db,
        org,
        assess,
        control_code="PR.AA-01",
        control_title="Identities and credentials",
        in_scope=True,
    )
    result = make_result(
        db,
        org,
        control,
        version_no=1,
        author_actor="agent",
        author_user_id=None,
        control_status="implemented",
        explanation="Attestation based.",
        evidence_pending=True,
    )
    make_review(db, org, result, user_a, outcome="accepted")

    source = DbReportSource()
    report_input = source.load(db, org.id, assess.id)
    assert report_input is not None

    view = build_report_view(report_input, datetime.now(timezone.utc))
    assert len(view.results) == 1
    assert view.results[0].basis == "accepted_agent_result"
    assert view.results[0].evidence_pending is True
    assert view.summary.final_with_evidence_pending == 1


def make_linked_file(
    db: Session,
    organization: Organization,
    control: AssessmentControl,
    name: str,
    created_at: datetime,
    *,
    sha256: str | None = None,
    linked_at: datetime | None = None,
) -> EvidenceFile:
    evidence = EvidenceFile(
        organization_id=organization.id,
        assessment_id=control.assessment_id,
        original_filename=name,
        stored_filename=f"{uuid.uuid4()}.pdf",
        content_type="application/pdf",
        file_extension=".pdf",
        size_bytes=2048,
        sha256=sha256 or uuid.uuid4().hex * 2,
        extracted_text="SECRET EXTRACTED TEXT that must never reach the report.",
        created_at=created_at,
    )
    db.add(evidence)
    db.flush()
    db.add(
        EvidenceControlLink(
            organization_id=organization.id,
            assessment_id=control.assessment_id,
            assessment_control_id=control.id,
            evidence_file_id=evidence.id,
            **({"created_at": linked_at} if linked_at is not None else {}),
        )
    )
    db.commit()
    return evidence


def test_linked_evidence_reaches_the_final_result_without_extracted_text(db):
    org = make_organization(db)
    reviewer = make_user(db)
    assess = make_assessment(db, org)
    control = make_control(db, org, assess, control_code="PR.AA-03", control_title="Users are authenticated")
    other = make_control(db, org, assess, control_code="PR.AA-05", control_title="Access is reviewed")
    result = make_result(db, org, control, control_status="implemented", evidence_refs=[], evidence_pending=True)
    make_review(db, org, result, reviewer, outcome="accepted")
    make_linked_file(db, org, control, "mfa-policy-v2.pdf", datetime(2026, 11, 16, 1, 50, tzinfo=timezone.utc))
    make_linked_file(db, org, control, "mfa-policy-v1.pdf", datetime(2026, 11, 16, 1, 40, tzinfo=timezone.utc))
    make_linked_file(db, org, other, "access-review.pdf", datetime(2026, 11, 16, 1, 45, tzinfo=timezone.utc))

    report_input = DbReportSource().load(db, org.id, assess.id)
    view = build_report_view(report_input, datetime.now(timezone.utc))

    (final,) = view.results
    assert final.code == "PR.AA-03"
    assert [f.file_name for f in final.linked_evidence] == ["mfa-policy-v1.pdf", "mfa-policy-v2.pdf"]
    assert final.linked_evidence[0].file_type == "PDF" and final.linked_evidence[0].size_bytes == 2048
    assert final.evidence_pending is True
    # PR.AA-05 has no reviewed result, so its file stays out of the report.
    exported = view.model_dump_json()
    assert "access-review.pdf" not in exported
    assert "SECRET EXTRACTED TEXT" not in exported

    pdf_text = " ".join(
        (page.extract_text() or "") for page in pdfplumber.open(BytesIO(render_report_pdf(view))).pages
    )
    assert "mfa-policy-v1.pdf" in pdf_text and "Not yet verified by Aligo" in pdf_text
    assert "SECRET EXTRACTED TEXT" not in pdf_text


def test_linked_evidence_marks_files_linked_after_the_review_and_keeps_duplicates_apart(db):
    org = make_organization(db)
    reviewer = make_user(db)
    assess = make_assessment(db, org)
    control = make_control(db, org, assess, control_code="PR.AA-03")
    result = make_result(db, org, control, control_status="implemented")
    reviewed_at = datetime(2026, 11, 10, 15, 0, tzinfo=timezone.utc)
    make_review(db, org, result, reviewer, outcome="accepted", reviewed_at=reviewed_at)
    same_content = "c" * 64
    first = make_linked_file(
        db, org, control, "mfa.pdf", datetime(2026, 11, 9, tzinfo=timezone.utc),
        sha256=same_content, linked_at=datetime(2026, 11, 9, tzinfo=timezone.utc),
    )
    second = make_linked_file(
        db, org, control, "mfa.pdf", datetime(2026, 11, 16, tzinfo=timezone.utc),
        sha256=same_content, linked_at=datetime(2026, 11, 16, tzinfo=timezone.utc),
    )

    view = build_report_view(DbReportSource().load(db, org.id, assess.id), datetime.now(timezone.utc))

    files = view.results[0].linked_evidence
    # The same file uploaded twice stays two entries, told apart by id.
    assert [f.id for f in files] == [first.id, second.id]
    assert [f.added_after_review for f in files] == [False, True]


def test_linked_evidence_of_another_assessment_is_not_shown(db):
    org = make_organization(db)
    reviewer = make_user(db)
    assess = make_assessment(db, org)
    other_assess = make_assessment(db, org)
    control = make_control(db, org, assess, control_code="PR.AA-03")
    other_control = make_control(db, org, other_assess, control_code="PR.AA-03")
    result = make_result(db, org, control, control_status="implemented")
    make_review(db, org, result, reviewer, outcome="accepted")
    make_linked_file(db, org, other_control, "other-assessment.pdf", datetime(2026, 11, 16, tzinfo=timezone.utc))

    view = build_report_view(DbReportSource().load(db, org.id, assess.id), datetime.now(timezone.utc))

    assert view.results[0].linked_evidence == []


def test_new_assessment_shows_its_kb_controls_as_pending(db):
    """An assessment started from the API has its KB controls in scope, all pending until results exist (AGRC-73)."""
    org = make_organization(db)
    consultant = make_user(db)

    assessment = start_assessment(db, org.id, consultant.id, AssessmentCreate(title="New assessment"))

    report_input = DbReportSource().load(db, org.id, assessment.id)
    assert report_input is not None
    view = build_report_view(report_input, datetime.now(timezone.utc))

    assert [(s.code, s.title) for s in view.scope] == controls_for_kb_version("demo-0.2")
    assert [(p.code, p.reason) for p in view.pending] == [
        ("PR.AA-01", "no_result"),
        ("PR.AA-03", "no_result"),
        ("PR.AA-05", "no_result"),
    ]
    assert view.results == []
    assert view.exclusions == []


def test_seed_demo_assessment_data_builds_the_expected_report(db):
    """The seed script's data satisfies every database rule and produces the table of spec 4.3."""
    org = make_organization(db)
    reviewer = make_user(db)

    assessment = seed_demo_assessment_data(db, org, reviewer)
    db.commit()

    report_input = DbReportSource().load(db, org.id, assessment.id)
    assert report_input is not None
    view = build_report_view(report_input, datetime.now(timezone.utc))

    assert [s.code for s in view.scope] == [
        "DE.CM-01",
        "ID.AM-01",
        "PR.AA-01",
        "PR.AA-03",
        "PR.AA-05",
        "PR.PS-06",
    ]
    assert [(r.code, r.control_status, r.basis, r.reviewed_by) for r in view.results] == [
        ("PR.AA-01", "implemented", "accepted_agent_result", "Aligo consultant"),
        ("PR.AA-03", "partially_implemented", "consultant_version", "Aligo consultant"),
    ]
    assert [(p.code, p.reason) for p in view.pending] == [
        ("DE.CM-01", "no_result"),
        ("ID.AM-01", "rejected_awaiting_new_version"),
        ("PR.AA-05", "awaiting_review"),
    ]
    assert [e.code for e in view.exclusions] == ["PR.PS-06"]

    # Every agent result carries its status_assessed trace, which the expert-review service requires.
    agent_results = db.scalars(
        select(ControlResult).where(
            ControlResult.assessment_id == assessment.id,
            ControlResult.author_actor == "agent",
        )
    ).all()
    assert len(agent_results) == 4
    assert all(result.trace_id is not None for result in agent_results)
    review_traces = db.scalars(
        select(DecisionTraceRecord).where(
            DecisionTraceRecord.assessment_id == assessment.id,
            DecisionTraceRecord.decision_type == "human_review",
        )
    ).all()
    assert len(review_traces) == 3


def test_report_never_contains_user_emails(db):
    """Client-facing report and PDF must never reveal consultant user emails."""
    org = make_organization(db)
    user_a = make_user(db)
    assess = make_assessment(db, org)

    # 1. PR.AA-01: agent v1 implemented + review accepted by user A
    c_aa01 = make_control(
        db,
        org,
        assess,
        control_code="PR.AA-01",
        control_title="Identities and credentials",
        in_scope=True,
    )
    r_aa01 = make_result(
        db,
        org,
        c_aa01,
        version_no=1,
        author_actor="agent",
        author_user_id=None,
        control_status="implemented",
        explanation="Identities managed centrally.",
    )
    make_review(
        db,
        org,
        r_aa01,
        user_a,
        outcome="accepted",
        comment="Confirmed by user A.",
    )

    # 2. PR.AA-03: agent v1 + review modified (resulting v2) + consultant v2 partially_implemented by user A
    c_aa03 = make_control(
        db,
        org,
        assess,
        control_code="PR.AA-03",
        control_title="Users authenticated",
        in_scope=True,
    )
    r_aa03_v1 = make_result(
        db,
        org,
        c_aa03,
        version_no=1,
        author_actor="agent",
        author_user_id=None,
        control_status="implemented",
        explanation="Agent proposal.",
    )
    r_aa03_v2 = make_result(
        db,
        org,
        c_aa03,
        version_no=2,
        based_on_result_id=r_aa03_v1.id,
        author_actor="aligo_consultant",
        author_user_id=user_a.id,
        control_status="partially_implemented",
        explanation="Consultant modified: MFA partial.",
    )
    make_review(
        db,
        org,
        r_aa03_v1,
        user_a,
        outcome="modified",
        resulting_result_id=r_aa03_v2.id,
        comment="Modified to partially implemented.",
    )

    # 3. PR.AA-05: agent v1 implemented, evidence_pending=True, no review
    c_aa05 = make_control(
        db,
        org,
        assess,
        control_code="PR.AA-05",
        control_title="Access permissions defined",
        in_scope=True,
    )
    make_result(
        db,
        org,
        c_aa05,
        version_no=1,
        author_actor="agent",
        author_user_id=None,
        control_status="implemented",
        explanation="Access managed.",
        evidence_pending=True,
    )

    # 4. ID.AM-01: agent v1 not_implemented + review rejected
    c_am01 = make_control(
        db,
        org,
        assess,
        control_code="ID.AM-01",
        control_title="Inventories maintained",
        in_scope=True,
    )
    r_am01 = make_result(
        db,
        org,
        c_am01,
        version_no=1,
        author_actor="agent",
        author_user_id=None,
        control_status="not_implemented",
        explanation="No inventory.",
    )
    make_review(
        db,
        org,
        r_am01,
        user_a,
        outcome="rejected",
        comment="Rejected: inventory exists.",
    )

    # 5. PR.PS-06: consultant v1 not_applicable with justification
    c_ps06 = make_control(
        db,
        org,
        assess,
        control_code="PR.PS-06",
        control_title="Secure software development",
        in_scope=True,
    )
    make_result(
        db,
        org,
        c_ps06,
        version_no=1,
        author_actor="aligo_consultant",
        author_user_id=user_a.id,
        control_status="not_applicable",
        explanation="No internal dev.",
        justification="Organization does not develop software in-house.",
    )

    # 6. DE.CM-01: in_scope=True, no results
    make_control(
        db,
        org,
        assess,
        control_code="DE.CM-01",
        control_title="Network monitoring",
        in_scope=True,
    )

    # 7. GV.OC-01: in_scope=False with rationale
    make_control(
        db,
        org,
        assess,
        control_code="GV.OC-01",
        control_title="Organizational context",
        in_scope=False,
        scope_rationale="Out of scope for this assessment.",
    )

    source = DbReportSource()
    report_input = source.load(db, org.id, assess.id)
    assert report_input is not None

    view = build_report_view(report_input, datetime.now(timezone.utc))
    pdf_bytes = render_report_pdf(view)

    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        pdf_text = " ".join((page.extract_text() or "") for page in pdf.pages)

    view_json = view.model_dump_json()
    assert user_a.email not in view_json
    assert user_a.email not in pdf_text

    # A long email can wrap inside a PDF table cell and stop being one contiguous string, so also
    # check for what survives wrapping: no "@" at all, and no trace of the address in the compact text.
    compact_pdf_text = "".join(pdf_text.split())
    assert "@" not in view_json
    assert "@" not in pdf_text
    assert "example.com" not in compact_pdf_text
    assert str(user_a.id) not in view_json

    # The neutral label is what the client sees instead.
    assert {r.reviewed_by for r in view.results} == {"Aligo consultant"}
    assert "Aligo consultant" in pdf_text
