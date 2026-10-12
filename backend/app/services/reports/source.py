from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import Organization
from app.schemas.report import (
    AssessmentInfo,
    ControlInScope,
    EvidenceReference,
    OrganizationInfo,
    ReportInput,
    ResultReview,
    ResultVersion,
)

DEMO_ASSESSMENT_ID = UUID("00000000-0000-4000-8000-000000000014")


class ReportDataSource(Protocol):
    def load(self, db: Session | None, organization_id: UUID, assessment_id: UUID) -> ReportInput | None:
        """Return the report input, or None if the assessment does not exist for that organization."""
        ...


class DemoReportSource:
    def load(self, db: Session | None, organization_id: UUID, assessment_id: UUID) -> ReportInput | None:
        if assessment_id != DEMO_ASSESSMENT_ID:
            return None
        if db is None:
            return None

        org = db.get(Organization, organization_id)
        if org is None:
            return None

        org_info = OrganizationInfo(
            id=organization_id,
            name=org.name,
            sector=org.industry_sector.label,
            size=org.organization_size.label,
        )

        assessment_info = AssessmentInfo(
            id=DEMO_ASSESSMENT_ID,
            title="Identity and access — demo assessment",
            framework="NIST CSF 2.0",
            kb_version="kb-demo-0.1",
            status="awaiting_review",
            started_at=datetime(2026, 1, 15, 9, 0, 0, tzinfo=timezone.utc),
            completed_at=None,
        )

        controls = [
            ControlInScope(
                code="PR.AA-01",
                title="Identities and credentials for authorized users, services, and hardware are managed by the organization",
                versions=[
                    ResultVersion(
                        version_no=1,
                        author_actor="agent",
                        control_status="implemented",
                        explanation="Identities and credentials are centrally managed through corporate directory services and single sign-on.",
                        confidence=0.92,
                        evidence=[
                            EvidenceReference(
                                source_type="document_span",
                                reference="Access Control Policy v2.pdf, p. 4, §3.2",
                                excerpt="All employee and service identities must be provisioned and maintained in the primary identity directory.",
                                nature="intent",
                            ),
                            EvidenceReference(
                                source_type="tenant_configuration",
                                reference="Okta Admin Console - Directory Integrations",
                                excerpt="Automated provisioning enabled with daily directory synchronization.",
                                nature="implementation",
                            ),
                        ],
                        evidence_pending=False,
                        created_at=datetime(2026, 1, 16, 10, 0, 0, tzinfo=timezone.utc),
                        review=ResultReview(
                            outcome="accepted",
                            reviewer_name="Aligo Consultant (demo)",
                            reviewed_at=datetime(2026, 1, 17, 14, 0, 0, tzinfo=timezone.utc),
                            comment="Identity governance controls and configuration evidence confirmed.",
                        ),
                    ),
                ],
            ),
            ControlInScope(
                code="PR.AA-03",
                title="Users, services, and hardware are authenticated",
                versions=[
                    ResultVersion(
                        version_no=1,
                        author_actor="agent",
                        control_status="implemented",
                        explanation="Multi-factor authentication is configured across identity provider policies.",
                        confidence=0.88,
                        created_at=datetime(2026, 1, 16, 10, 30, 0, tzinfo=timezone.utc),
                        review=ResultReview(
                            outcome="modified",
                            reviewer_name="Aligo Consultant (demo)",
                            reviewed_at=datetime(2026, 1, 17, 14, 30, 0, tzinfo=timezone.utc),
                            comment="MFA covers standard users but admin account enforcement is incomplete.",
                        ),
                    ),
                    ResultVersion(
                        version_no=2,
                        author_actor="aligo_consultant",
                        author_name="Aligo Consultant (demo)",
                        control_status="partially_implemented",
                        explanation="MFA is enforced for standard users; however, MFA covers only part of admin accounts on legacy infrastructure.",
                        evidence=[
                            EvidenceReference(
                                source_type="tenant_configuration",
                                reference="Azure AD Conditional Access Policy Report",
                                excerpt="Legacy administrative portals allow single-factor authentication.",
                                nature="implementation",
                            ),
                        ],
                        evidence_pending=False,
                        created_at=datetime(2026, 1, 17, 15, 0, 0, tzinfo=timezone.utc),
                    ),
                ],
            ),
            ControlInScope(
                code="PR.AA-05",
                title="Access permissions, entitlements, and authorizations are defined in a policy, managed, enforced, and reviewed",
                versions=[
                    ResultVersion(
                        version_no=1,
                        author_actor="agent",
                        control_status="implemented",
                        explanation="Access control policy defines entitlement assignment and periodic review workflows.",
                        confidence=0.75,
                        evidence=[
                            EvidenceReference(
                                source_type="interview_turn",
                                reference="GRC Lead Interview, Turn 12",
                                excerpt="We perform quarterly user access reviews across all critical databases.",
                                nature="attestation",
                            ),
                        ],
                        evidence_pending=True,
                        created_at=datetime(2026, 1, 16, 11, 0, 0, tzinfo=timezone.utc),
                        review=None,
                    ),
                ],
            ),
            ControlInScope(
                code="ID.AM-01",
                title="Inventories of hardware managed by the organization are maintained",
                versions=[
                    ResultVersion(
                        version_no=1,
                        author_actor="agent",
                        control_status="not_implemented",
                        explanation="No active hardware inventory system was discovered in the uploaded artifacts.",
                        confidence=0.60,
                        created_at=datetime(2026, 1, 16, 11, 30, 0, tzinfo=timezone.utc),
                        review=ResultReview(
                            outcome="rejected",
                            reviewer_name="Aligo Consultant (demo)",
                            reviewed_at=datetime(2026, 1, 17, 16, 0, 0, tzinfo=timezone.utc),
                            comment="Rejected: Asset tracking is handled in Snipe-IT; evidence was omitted during interview.",
                        ),
                    ),
                ],
            ),
            ControlInScope(
                code="PR.PS-06",
                title="Secure software development practices are integrated, and their performance is monitored throughout the software development life cycle",
                versions=[
                    ResultVersion(
                        version_no=1,
                        author_actor="aligo_consultant",
                        author_name="Aligo Consultant (demo)",
                        control_status="not_applicable",
                        explanation="The organization operates as a service provider using third-party SaaS applications exclusively.",
                        justification="organization does not develop software in-house",
                        created_at=datetime(2026, 1, 17, 16, 30, 0, tzinfo=timezone.utc),
                    ),
                ],
            ),
            ControlInScope(
                code="DE.CM-01",
                title="Networks and network services are monitored to find potentially adverse events",
                versions=[],
            ),
        ]

        return ReportInput(
            organization=org_info,
            assessment=assessment_info,
            controls=controls,
            is_demo_data=True,
        )


def get_report_source() -> ReportDataSource:
    return DemoReportSource()
