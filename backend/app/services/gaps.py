"""Gap list of an assessment, ordered by criticality (HU-17).

A gap is a control whose final result is partially or not implemented. The final result is
decided exactly as in the report (app/services/reports/builder.py): only results confirmed by a
consultant count, so the gap list and the report never disagree, and an unreviewed agent draft
is not a gap yet.

Each gap gets its priority and risks from the rule in risk_classification.py. A control without
a rule is listed as not classified instead of failing the whole list or getting an invented
priority. When the HU-16 gap findings exist, they can replace the control results as the input.
"""

from datetime import datetime

from app.schemas.gaps import Gap, GapList, GapRisk
from app.schemas.report import ReportInput, ReportView
from app.services.reports.builder import build_report_view
from app.services.risk_classification import (
    GAP_STATUS_ORDER,
    RULE_ID,
    RULE_VERSION,
    RULES_PROVISIONAL,
    classify_gap,
    order_gaps,
)


def build_gap_list(
    data: ReportInput, generated_at: datetime, view: ReportView | None = None
) -> GapList:
    """The gap list of an assessment.

    Pass the view when the report view of the same data is already built, so it is not built
    twice and the gap list is guaranteed to match it.
    """
    if view is None:
        view = build_report_view(data, generated_at)
    latest_version = {
        control.code: max(version.version_no for version in control.versions)
        for control in data.controls
        if control.versions
    }

    final_gaps = [
        result for result in view.results if result.control_status in GAP_STATUS_ORDER
    ]
    by_code = {result.code: result for result in final_gaps}

    classified = []
    unclassified = []
    for result in final_gaps:
        try:
            classified.append(classify_gap(result.code, result.control_status))
        except ValueError:
            unclassified.append(result)

    gaps = []
    for classification in order_gaps(classified):
        result = by_code[classification.control_code]
        gaps.append(
            Gap(
                control_code=result.code,
                control_title=result.title,
                control_status=result.control_status,
                status_label=result.status_label,
                classified=True,
                priority=classification.priority,
                risks=[
                    GapRisk(name=name, severity=severity)
                    for name, severity in classification.risks
                ],
                reason=classification.reason,
                result_version=latest_version[result.code],
                basis=result.basis,
                explanation=result.explanation,
                evidence_pending=result.evidence_pending,
            )
        )
    for result in sorted(unclassified, key=lambda item: item.code):
        gaps.append(
            Gap(
                control_code=result.code,
                control_title=result.title,
                control_status=result.control_status,
                status_label=result.status_label,
                classified=False,
                result_version=latest_version[result.code],
                basis=result.basis,
                explanation=result.explanation,
                evidence_pending=result.evidence_pending,
            )
        )

    return GapList(
        organization_id=data.organization.id,
        assessment_id=data.assessment.id,
        generated_at=generated_at,
        rules_id=RULE_ID,
        rules_version=RULE_VERSION,
        rules_provisional=RULES_PROVISIONAL,
        gaps=gaps,
        pending_controls=view.summary.pending,
    )
