"""Compare an assessment with an earlier completed one of the same organization (HU-24).

Both sides come from report views, so the comparison uses exactly the final results, exclusions and
compliance figure (HU-23) that each report shows. Drafts and unreviewed agent results never enter it.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Assessment
from app.schemas.report import (
    AssessmentComparison,
    ComparedAssessment,
    ComparisonCandidate,
    ComparisonChange,
    ComparisonScope,
    ComparisonWarning,
    ControlComparison,
    ReportView,
)

PENDING_STATUS = "pending"  # the control has no final result in that assessment

# Only these statuses are ordered. Any other pair of different statuses is "not_comparable".
_STATUS_RANK = {"not_implemented": 0, "partially_implemented": 1, "implemented": 2}


def _framework_label(assessment: Assessment) -> str:
    if assessment.framework_code == "NIST-CSF":
        return "NIST CSF " + assessment.framework_version
    return f"{assessment.framework_code} {assessment.framework_version}"


def list_comparison_candidates(
    db: Session | None, organization_id: UUID, assessment_id: UUID
) -> list[ComparisonCandidate]:
    """Earlier completed assessments of the same organization, most recently completed first.

    "Earlier" means created before the current assessment. Both ids are filtered together, so an
    assessment of another organization is never listed.
    """
    if db is None:
        return []
    current = db.scalar(
        select(Assessment).where(
            Assessment.id == assessment_id,
            Assessment.organization_id == organization_id,
        )
    )
    if current is None:
        return []

    rows = db.scalars(
        select(Assessment)
        .where(
            Assessment.organization_id == organization_id,
            Assessment.id != assessment_id,
            Assessment.status == "completed",
            Assessment.created_at < current.created_at,
        )
        .order_by(Assessment.completed_at.desc(), Assessment.created_at.desc())
    )
    return [
        ComparisonCandidate(
            id=row.id,
            title=row.title,
            completed_at=row.completed_at,
            framework=_framework_label(row),
            kb_version=row.kb_version,
        )
        for row in rows
    ]


def final_statuses(view: ReportView) -> dict[str, str]:
    """Control code -> final status in a report view ("pending" when it has no final result)."""
    statuses = {item.code: item.control_status for item in view.results}
    statuses.update({item.code: "not_applicable" for item in view.exclusions})
    statuses.update({item.code: PENDING_STATUS for item in view.pending})
    return statuses


def classify_change(previous_status: str, current_status: str) -> ComparisonChange:
    if previous_status == current_status:
        return "unchanged"
    if previous_status in _STATUS_RANK and current_status in _STATUS_RANK:
        if _STATUS_RANK[current_status] > _STATUS_RANK[previous_status]:
            return "improved"
        return "declined"
    return "not_comparable"


def _compared(view: ReportView) -> ComparedAssessment:
    return ComparedAssessment(
        id=view.assessment.id,
        title=view.assessment.title,
        status=view.assessment.status,
        completed_at=view.assessment.completed_at,
        framework=view.assessment.framework,
        kb_version=view.assessment.kb_version,
        compliance=view.summary.compliance,
    )


def build_comparison(current: ReportView, previous: ReportView) -> AssessmentComparison:
    current_statuses = final_statuses(current)
    previous_statuses = final_statuses(previous)
    titles = {item.code: item.title for item in previous.scope}
    titles.update({item.code: item.title for item in current.scope})

    current_codes = {item.code for item in current.scope}
    previous_codes = {item.code for item in previous.scope}
    common = sorted(current_codes & previous_codes)
    scope = ComparisonScope(
        added=sorted(current_codes - previous_codes),
        removed=sorted(previous_codes - current_codes),
        common=len(common),
    )

    controls = [
        ControlComparison(
            code=code,
            title=titles[code],
            previous_status=previous_statuses[code],
            current_status=current_statuses[code],
            change=classify_change(previous_statuses[code], current_statuses[code]),
        )
        for code in common
    ]

    current_info = _compared(current)
    previous_info = _compared(previous)

    warnings: list[ComparisonWarning] = []
    if current.assessment.status != "completed":
        warnings.append(
            ComparisonWarning(
                code="current_not_completed",
                message="The current assessment is not completed yet, so its results can still change.",
            )
        )
    if current.assessment.framework != previous.assessment.framework:
        warnings.append(
            ComparisonWarning(
                code="framework_differs",
                message=(
                    f"The assessments use different frameworks ({previous.assessment.framework} and "
                    f"{current.assessment.framework}), so they are not directly equivalent."
                ),
            )
        )
    if current.assessment.kb_version != previous.assessment.kb_version:
        warnings.append(
            ComparisonWarning(
                code="kb_version_differs",
                message=(
                    f"The assessments use different knowledge base versions ({previous.assessment.kb_version} "
                    f"and {current.assessment.kb_version}), so they are not directly equivalent."
                ),
            )
        )
    if scope.added or scope.removed:
        warnings.append(
            ComparisonWarning(
                code="scope_differs",
                message=(
                    f"The scope differs: {len(scope.added)} control(s) only in the current assessment and "
                    f"{len(scope.removed)} only in the previous one. Only the {scope.common} common "
                    "control(s) are compared one by one."
                ),
            )
        )

    current_compliance = current_info.compliance
    previous_compliance = previous_info.compliance
    change_pct = None
    if (
        current_compliance is not None
        and previous_compliance is not None
        and current_compliance.available
        and previous_compliance.available
    ):
        change_pct = round(current_compliance.value_pct - previous_compliance.value_pct, 1)
    else:
        warnings.append(
            ComparisonWarning(
                code="compliance_unavailable",
                message="The compliance figure is unavailable for at least one assessment, so no change is shown.",
            )
        )

    return AssessmentComparison(
        current=current_info,
        previous=previous_info,
        compliance_change_pct=change_pct,
        warnings=warnings,
        scope=scope,
        changed_controls=sum(1 for item in controls if item.change != "unchanged"),
        controls=controls,
    )
