"""Seed one demo assessment (7 controls, results, reviews and traces) for an existing organization.

Usage (from backend/):
    python -m scripts.seed_demo_assessment --organization-id <uuid> --reviewer-email <email> --confirm

Meant for local databases. Running it against the shared Supabase database is a team decision, not an
individual one. The rows it writes to control_results, control_result_reviews and decision_traces are
append-only: once committed they cannot be updated or deleted.
"""

import argparse
import sys
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    Assessment,
    AssessmentControl,
    ControlResult,
    ControlResultReview,
    Organization,
    User,
)
from app.db.session import get_engine
from app.schemas.decision_trace import DecisionTrace, TraceSource
from app.services.decision_traces import record_trace

APPEND_ONLY_NOTICE = (
    "Running this against the shared Supabase database is a team decision.\n"
    "The seeded rows in control_results, control_result_reviews and decision_traces are append-only\n"
    "and cannot be deleted afterwards."
)


def seed_demo_assessment_data(
    db: Session,
    organization: Organization,
    reviewer: User,
) -> Assessment:
    """Creates one assessment with the 7-control set (matching test 4.3 and realistic demo text).

    Everything is added and flushed in the given session without committing.
    """
    assessment = Assessment(
        id=uuid4(),
        organization_id=organization.id,
        title="Identity and access — assessment",
        framework_code="NIST-CSF",
        framework_version="2.0",
        kb_version="demo-0.2",
        status="awaiting_review",
        started_at=datetime(2026, 1, 15, 9, 0, 0, tzinfo=timezone.utc),
        completed_at=None,
    )
    db.add(assessment)
    db.flush()

    # 1. PR.AA-01: agent v1 implemented + review accepted by reviewer
    c1 = AssessmentControl(
        organization_id=organization.id,
        assessment_id=assessment.id,
        control_code="PR.AA-01",
        control_title="Identities and credentials for authorized users, services, and hardware are managed by the organization",
        in_scope=True,
    )
    db.add(c1)
    db.flush()

    trace_c1 = record_trace(
        db,
        DecisionTrace(
            organization_id=organization.id,
            assessment_id=assessment.id,
            decision_type="status_assessed",
            control_ids=["PR.AA-01"],
            actor_type="agent",
            prompt_id="rule:seed-demo",
            prompt_version="0.1.0",
            kb_version=assessment.kb_version,
            sources=[
                TraceSource(
                    type="document_span",
                    ref="Access Control Policy v2.pdf, p. 4, §3.2",
                    excerpt="All employee and service identities must be provisioned and maintained in the primary identity directory.",
                )
            ],
            output={"status": "implemented"},
            rationale="Identities and credentials are centrally managed through corporate directory services and single sign-on.",
            confidence=0.92,
        ),
    )

    r1 = ControlResult(
        organization_id=organization.id,
        assessment_id=assessment.id,
        assessment_control_id=c1.id,
        version_no=1,
        author_actor="agent",
        author_user_id=None,
        control_status="implemented",
        explanation="Identities and credentials are centrally managed through corporate directory services and single sign-on.",
        confidence=0.92,
        evidence_pending=False,
        evidence_refs=[
            {
                "source_type": "document_span",
                "reference": "Access Control Policy v2.pdf, p. 4, §3.2",
                "excerpt": "All employee and service identities must be provisioned and maintained in the primary identity directory.",
                "nature": "intent",
            },
            {
                "source_type": "tenant_configuration",
                "reference": "Okta Admin Console - Directory Integrations",
                "excerpt": "Automated provisioning enabled with daily directory synchronization.",
                "nature": "implementation",
            },
        ],
        trace_id=trace_c1.id,
        created_at=datetime(2026, 1, 16, 10, 0, 0, tzinfo=timezone.utc),
    )
    db.add(r1)
    db.flush()

    rev_trace_c1 = record_trace(
        db,
        DecisionTrace(
            organization_id=organization.id,
            assessment_id=assessment.id,
            decision_type="human_review",
            control_ids=["PR.AA-01"],
            actor_type="aligo_consultant",
            actor_user_id=reviewer.id,
            kb_version=assessment.kb_version,
            sources=[],
            output={
                "control_result_id": str(r1.id),
                "outcome": "accepted",
                "comment": "Identity governance controls and configuration evidence confirmed.",
            },
            rationale="Identity governance controls and configuration evidence confirmed.",
            reviews_trace_id=trace_c1.id,
            review_outcome="accepted",
        ),
    )

    rev1 = ControlResultReview(
        organization_id=organization.id,
        assessment_id=assessment.id,
        control_result_id=r1.id,
        outcome="accepted",
        resulting_result_id=None,
        comment="Identity governance controls and configuration evidence confirmed.",
        reviewed_by_user_id=reviewer.id,
        review_trace_id=rev_trace_c1.id,
        reviewed_at=datetime(2026, 1, 17, 14, 0, 0, tzinfo=timezone.utc),
    )
    db.add(rev1)
    db.flush()

    # 2. PR.AA-03: agent v1 + review modified (resulting v2) + consultant v2 partially_implemented
    c2 = AssessmentControl(
        organization_id=organization.id,
        assessment_id=assessment.id,
        control_code="PR.AA-03",
        control_title="Users, services, and hardware are authenticated",
        in_scope=True,
    )
    db.add(c2)
    db.flush()

    trace_c2 = record_trace(
        db,
        DecisionTrace(
            organization_id=organization.id,
            assessment_id=assessment.id,
            decision_type="status_assessed",
            control_ids=["PR.AA-03"],
            actor_type="agent",
            prompt_id="rule:seed-demo",
            prompt_version="0.1.0",
            kb_version=assessment.kb_version,
            sources=[
                TraceSource(
                    type="tenant_configuration",
                    ref="Azure AD Conditional Access Policy Report",
                    excerpt="Legacy administrative portals allow single-factor authentication.",
                )
            ],
            output={"status": "implemented"},
            rationale="Multi-factor authentication is configured across identity provider policies.",
            confidence=0.88,
        ),
    )

    r2_v1 = ControlResult(
        organization_id=organization.id,
        assessment_id=assessment.id,
        assessment_control_id=c2.id,
        version_no=1,
        author_actor="agent",
        author_user_id=None,
        control_status="implemented",
        explanation="Multi-factor authentication is configured across identity provider policies.",
        confidence=0.88,
        evidence_pending=False,
        trace_id=trace_c2.id,
        created_at=datetime(2026, 1, 16, 10, 30, 0, tzinfo=timezone.utc),
    )
    db.add(r2_v1)
    db.flush()

    # Same order as the real review flow (app/services/expert_reviews.py): control_results is append-only,
    # so the consultant version gets its id up front and is inserted with trace_id already set.
    r2_v2_id = uuid4()

    rev_trace_c2 = record_trace(
        db,
        DecisionTrace(
            organization_id=organization.id,
            assessment_id=assessment.id,
            decision_type="human_review",
            control_ids=["PR.AA-03"],
            actor_type="aligo_consultant",
            actor_user_id=reviewer.id,
            kb_version=assessment.kb_version,
            sources=[],
            output={
                "control_result_id": str(r2_v1.id),
                "outcome": "modified",
                "resulting_result_id": str(r2_v2_id),
                "comment": "MFA covers standard users but admin account enforcement is incomplete.",
            },
            rationale="MFA covers standard users but admin account enforcement is incomplete.",
            reviews_trace_id=trace_c2.id,
            review_outcome="modified",
        ),
    )

    r2_v2 = ControlResult(
        id=r2_v2_id,
        organization_id=organization.id,
        assessment_id=assessment.id,
        assessment_control_id=c2.id,
        version_no=2,
        based_on_result_id=r2_v1.id,
        author_actor="aligo_consultant",
        author_user_id=reviewer.id,
        control_status="partially_implemented",
        explanation="MFA is enforced for standard users; however, MFA covers only part of admin accounts on legacy infrastructure.",
        evidence_pending=False,
        evidence_refs=[
            {
                "source_type": "tenant_configuration",
                "reference": "Azure AD Conditional Access Policy Report",
                "excerpt": "Legacy administrative portals allow single-factor authentication.",
                "nature": "implementation",
            }
        ],
        trace_id=rev_trace_c2.id,
        created_at=datetime(2026, 1, 17, 15, 0, 0, tzinfo=timezone.utc),
    )
    db.add(r2_v2)
    db.flush()

    rev2 = ControlResultReview(
        organization_id=organization.id,
        assessment_id=assessment.id,
        control_result_id=r2_v1.id,
        outcome="modified",
        resulting_result_id=r2_v2.id,
        comment="MFA covers standard users but admin account enforcement is incomplete.",
        reviewed_by_user_id=reviewer.id,
        review_trace_id=rev_trace_c2.id,
        reviewed_at=datetime(2026, 1, 17, 14, 30, 0, tzinfo=timezone.utc),
    )
    db.add(rev2)
    db.flush()

    # 3. PR.AA-05: agent v1 implemented, evidence_pending=True, no review
    c3 = AssessmentControl(
        organization_id=organization.id,
        assessment_id=assessment.id,
        control_code="PR.AA-05",
        control_title="Access permissions, entitlements, and authorizations are defined in a policy, managed, enforced, and reviewed",
        in_scope=True,
    )
    db.add(c3)
    db.flush()

    trace_c3 = record_trace(
        db,
        DecisionTrace(
            organization_id=organization.id,
            assessment_id=assessment.id,
            decision_type="status_assessed",
            control_ids=["PR.AA-05"],
            actor_type="agent",
            prompt_id="rule:seed-demo",
            prompt_version="0.1.0",
            kb_version=assessment.kb_version,
            sources=[
                TraceSource(
                    type="interview_turn",
                    ref="GRC Lead Interview, Turn 12",
                    excerpt="We perform quarterly user access reviews across all critical databases.",
                )
            ],
            output={"status": "implemented"},
            rationale="Access control policy defines entitlement assignment and periodic review workflows.",
            confidence=0.75,
        ),
    )

    r3 = ControlResult(
        organization_id=organization.id,
        assessment_id=assessment.id,
        assessment_control_id=c3.id,
        version_no=1,
        author_actor="agent",
        author_user_id=None,
        control_status="implemented",
        explanation="Access control policy defines entitlement assignment and periodic review workflows.",
        confidence=0.75,
        evidence_pending=True,
        evidence_refs=[
            {
                "source_type": "interview_turn",
                "reference": "GRC Lead Interview, Turn 12",
                "excerpt": "We perform quarterly user access reviews across all critical databases.",
                "nature": "attestation",
            }
        ],
        trace_id=trace_c3.id,
        created_at=datetime(2026, 1, 16, 11, 0, 0, tzinfo=timezone.utc),
    )
    db.add(r3)
    db.flush()

    # 4. ID.AM-01: agent v1 not_implemented + review rejected
    c4 = AssessmentControl(
        organization_id=organization.id,
        assessment_id=assessment.id,
        control_code="ID.AM-01",
        control_title="Inventories of hardware managed by the organization are maintained",
        in_scope=True,
    )
    db.add(c4)
    db.flush()

    trace_c4 = record_trace(
        db,
        DecisionTrace(
            organization_id=organization.id,
            assessment_id=assessment.id,
            decision_type="status_assessed",
            control_ids=["ID.AM-01"],
            actor_type="agent",
            prompt_id="rule:seed-demo",
            prompt_version="0.1.0",
            kb_version=assessment.kb_version,
            sources=[
                TraceSource(
                    type="document_span",
                    ref="Hardware Inventory",
                    excerpt="No active hardware inventory system discovered.",
                )
            ],
            output={"status": "not_implemented"},
            rationale="No active hardware inventory system was discovered in the uploaded artifacts.",
            confidence=0.60,
        ),
    )

    r4 = ControlResult(
        organization_id=organization.id,
        assessment_id=assessment.id,
        assessment_control_id=c4.id,
        version_no=1,
        author_actor="agent",
        author_user_id=None,
        control_status="not_implemented",
        explanation="No active hardware inventory system was discovered in the uploaded artifacts.",
        confidence=0.60,
        evidence_pending=False,
        trace_id=trace_c4.id,
        created_at=datetime(2026, 1, 16, 11, 30, 0, tzinfo=timezone.utc),
    )
    db.add(r4)
    db.flush()

    rev_trace_c4 = record_trace(
        db,
        DecisionTrace(
            organization_id=organization.id,
            assessment_id=assessment.id,
            decision_type="human_review",
            control_ids=["ID.AM-01"],
            actor_type="aligo_consultant",
            actor_user_id=reviewer.id,
            kb_version=assessment.kb_version,
            sources=[],
            output={
                "control_result_id": str(r4.id),
                "outcome": "rejected",
                "comment": "Rejected: Asset tracking is handled in Snipe-IT; evidence was omitted during interview.",
            },
            rationale="Rejected: Asset tracking is handled in Snipe-IT; evidence was omitted during interview.",
            reviews_trace_id=trace_c4.id,
            review_outcome="rejected",
        ),
    )

    rev4 = ControlResultReview(
        organization_id=organization.id,
        assessment_id=assessment.id,
        control_result_id=r4.id,
        outcome="rejected",
        resulting_result_id=None,
        comment="Rejected: Asset tracking is handled in Snipe-IT; evidence was omitted during interview.",
        reviewed_by_user_id=reviewer.id,
        review_trace_id=rev_trace_c4.id,
        reviewed_at=datetime(2026, 1, 17, 16, 0, 0, tzinfo=timezone.utc),
    )
    db.add(rev4)
    db.flush()

    # 5. PR.PS-06: consultant v1 not_applicable with justification
    c5 = AssessmentControl(
        organization_id=organization.id,
        assessment_id=assessment.id,
        control_code="PR.PS-06",
        control_title="Secure software development practices are integrated, and their performance is monitored throughout the software development life cycle",
        in_scope=True,
    )
    db.add(c5)
    db.flush()

    r5 = ControlResult(
        organization_id=organization.id,
        assessment_id=assessment.id,
        assessment_control_id=c5.id,
        version_no=1,
        author_actor="aligo_consultant",
        author_user_id=reviewer.id,
        control_status="not_applicable",
        explanation="The organization operates as a service provider using third-party SaaS applications exclusively.",
        justification="organization does not develop software in-house",
        created_at=datetime(2026, 1, 17, 16, 30, 0, tzinfo=timezone.utc),
    )
    db.add(r5)
    db.flush()

    # 6. DE.CM-01: in_scope=True, no results
    c6 = AssessmentControl(
        organization_id=organization.id,
        assessment_id=assessment.id,
        control_code="DE.CM-01",
        control_title="Networks and network services are monitored to find potentially adverse events",
        in_scope=True,
    )
    db.add(c6)
    db.flush()

    # 7. GV.OC-01: in_scope=False with rationale
    c7 = AssessmentControl(
        organization_id=organization.id,
        assessment_id=assessment.id,
        control_code="GV.OC-01",
        control_title="The organizational mission, objectives, stakeholders, and activities are understood and prioritized",
        in_scope=False,
        scope_rationale="Out of scope for this assessment.",
    )
    db.add(c7)
    db.flush()

    return assessment


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed demo assessment with 7 controls for local demo.",
        epilog=APPEND_ONLY_NOTICE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--organization-id",
        required=True,
        type=UUID,
        help="Organization UUID",
    )
    parser.add_argument(
        "--reviewer-email",
        required=True,
        type=str,
        help="Reviewer user email",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm execution against the target database",
    )
    args = parser.parse_args()

    settings = get_settings()
    print(f"Database host: {settings.db_host}")
    print(f"Database name: {settings.db_name}")
    print(APPEND_ONLY_NOTICE)

    if not args.confirm:
        print("Aborted: --confirm is required to seed the demo assessment.")
        sys.exit(1)

    if settings.app_environment == "production":
        print("Refusing to run: cannot seed demo assessment in production environment.")
        sys.exit(1)

    engine = get_engine()
    with Session(engine) as session:
        normalized_email = args.reviewer_email.strip().lower()
        reviewer = session.scalar(
            select(User).where(func.lower(func.btrim(User.email)) == normalized_email)
        )
        if reviewer is None:
            print(f"Error: Reviewer with email '{args.reviewer_email}' not found in users table.")
            sys.exit(1)

        org = session.get(Organization, args.organization_id)
        if org is None:
            print(f"Error: Organization with id '{args.organization_id}' not found.")
            sys.exit(1)

        assessment = seed_demo_assessment_data(session, org, reviewer)
        session.commit()
        print(f"Successfully seeded demo assessment: {assessment.id}")


if __name__ == "__main__":
    main()
