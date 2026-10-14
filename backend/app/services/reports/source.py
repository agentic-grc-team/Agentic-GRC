import logging
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    Assessment,
    AssessmentControl,
    ControlResult,
    ControlResultReview,
    Organization,
)
from app.schemas.report import (
    AssessmentInfo,
    ControlInScope,
    EvidenceReference,
    OrganizationInfo,
    ReportInput,
    ResultReview,
    ResultVersion,
)

logger = logging.getLogger(__name__)

DEMO_ASSESSMENT_ID = UUID("00000000-0000-4000-8000-000000000014")
CONSULTANT_DISPLAY_NAME = "Aligo consultant"


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


class DbReportSource:
    def load(
        self, db: Session | None, organization_id: UUID, assessment_id: UUID
    ) -> ReportInput | None:
        if db is None:
            return None

        # 1. Filter by BOTH ids so another organization's assessment can never be read.
        assessment = db.scalar(
            select(Assessment).where(
                Assessment.id == assessment_id,
                Assessment.organization_id == organization_id,
            )
        )
        if assessment is None:
            return None

        # 2. Organization
        org = db.get(Organization, organization_id)
        if org is None:
            return None

        org_info = OrganizationInfo(
            id=organization_id,
            name=org.name,
            sector=org.industry_sector.label,
            size=org.organization_size.label,
        )

        # 3. AssessmentInfo
        if assessment.framework_code == "NIST-CSF":
            framework = "NIST CSF " + assessment.framework_version
        else:
            framework = f"{assessment.framework_code} {assessment.framework_version}"

        assessment_info = AssessmentInfo(
            id=assessment.id,
            title=assessment.title,
            framework=framework,
            kb_version=assessment.kb_version,
            status=assessment.status,
            started_at=assessment.started_at,
            completed_at=assessment.completed_at,
        )

        # 4. Controls in scope (ordered by control_code)
        controls = list(
            db.scalars(
                select(AssessmentControl)
                .where(
                    AssessmentControl.organization_id == organization_id,
                    AssessmentControl.assessment_id == assessment_id,
                    AssessmentControl.in_scope.is_(True),
                )
                .order_by(AssessmentControl.control_code)
            )
        )

        # 5. Results and reviews in bulk (no per-control queries).
        control_ids = [c.id for c in controls]
        if control_ids:
            results = list(
                db.scalars(
                    select(ControlResult)
                    .where(
                        ControlResult.organization_id == organization_id,
                        ControlResult.assessment_id == assessment_id,
                        ControlResult.assessment_control_id.in_(control_ids),
                    )
                    .order_by(ControlResult.assessment_control_id, ControlResult.version_no)
                )
            )
        else:
            results = []

        result_ids = [r.id for r in results]
        if result_ids:
            reviews = list(
                db.scalars(
                    select(ControlResultReview).where(
                        ControlResultReview.organization_id == organization_id,
                        ControlResultReview.assessment_id == assessment_id,
                        ControlResultReview.control_result_id.in_(result_ids),
                    )
                )
            )
        else:
            reviews = []

        reviews_by_result_id = {rev.control_result_id: rev for rev in reviews}

        # 6. Map each ControlResult to ResultVersion
        versions_by_control_id: dict[UUID, list[ResultVersion]] = {c.id: [] for c in controls}

        for result in results:
            # Reports go to the client: show a neutral label, never the consultant's email. Use a display name here once users have one.
            author_name = (
                CONSULTANT_DISPLAY_NAME if result.author_actor == "aligo_consultant" else None
            )

            review = None
            if result.author_actor == "agent":
                rev = reviews_by_result_id.get(result.id)
                if rev is not None:
                    review = ResultReview(
                        outcome=rev.outcome,
                        reviewer_name=CONSULTANT_DISPLAY_NAME,
                        reviewed_at=rev.reviewed_at,
                        comment=rev.comment or "",
                    )

            evidence_items: list[EvidenceReference] = []
            for item in (result.evidence_refs or []):
                # Warnings name the result and the failing fields only: evidence text must not end up in logs.
                if not isinstance(item, dict):
                    logger.warning(
                        "Skipping evidence reference in result %s: expected an object, got %s",
                        result.id,
                        type(item).__name__,
                    )
                    continue
                try:
                    raw_excerpt = item.get("excerpt")
                    if raw_excerpt is not None and isinstance(raw_excerpt, str) and len(raw_excerpt) > 300:
                        raw_excerpt = raw_excerpt[:297] + "..."
                    ev = EvidenceReference(
                        source_type=item.get("source_type"),
                        reference=item.get("reference"),
                        excerpt=raw_excerpt,
                        nature=item.get("nature"),
                    )
                    evidence_items.append(ev)
                except ValidationError as exc:
                    logger.warning(
                        "Skipping invalid evidence reference in result %s: invalid fields %s",
                        result.id,
                        sorted({".".join(str(part) for part in error["loc"]) for error in exc.errors()}),
                    )

            version = ResultVersion(
                version_no=result.version_no,
                author_actor=result.author_actor,
                author_name=author_name,
                control_status=result.control_status,
                explanation=result.explanation,
                justification=result.justification,
                not_assessed_reason=result.not_assessed_reason,
                confidence=float(result.confidence) if result.confidence is not None else None,
                evidence=evidence_items,
                evidence_pending=bool(result.evidence_pending),
                created_at=result.created_at,
                review=review,
            )

            if result.assessment_control_id in versions_by_control_id:
                versions_by_control_id[result.assessment_control_id].append(version)

        controls_in_scope = [
            ControlInScope(
                code=control.control_code,
                title=control.control_title,
                versions=versions_by_control_id[control.id],
            )
            for control in controls
        ]

        # 7. Return ReportInput
        return ReportInput(
            organization=org_info,
            assessment=assessment_info,
            controls=controls_in_scope,
            is_demo_data=False,
        )


class CompositeReportSource:
    """Demo assessment outside production; real data otherwise."""

    def __init__(self, allow_demo: bool) -> None:
        self._demo = DemoReportSource()
        self._db = DbReportSource()
        self._allow_demo = allow_demo

    def load(
        self, db: Session | None, organization_id: UUID, assessment_id: UUID
    ) -> ReportInput | None:
        if assessment_id == DEMO_ASSESSMENT_ID:
            return self._demo.load(db, organization_id, assessment_id) if self._allow_demo else None
        return self._db.load(db, organization_id, assessment_id)


def get_report_source() -> ReportDataSource:
    settings = get_settings()
    return CompositeReportSource(
        allow_demo=settings.allow_demo_report and settings.app_environment != "production"
    )

