"""Report view builder for Agentic GRC assessments.

Resolution rule:
    For each control in scope, the version with the highest version_no decides its state.

Evidence-pending rule:
    Consultant acceptance (or a consultant-authored version) is enough to make a result final.
    If the result's evidence_pending flag is True, it stays final but is always marked "evidence pending"
    wherever it appears, and counted separately. Evidence validation (E3, HU-13/HU-14) will later clear the
    flag; until then the report must never present such a result as evidence-backed.
"""

from datetime import datetime

from app.schemas.report import (
    Exclusion,
    FinalResult,
    PendingItem,
    ReportInput,
    ReportSummary,
    ReportView,
    ScopeItem,
    STATUS_LABELS,
    PENDING_REASON_LABELS,
)


def build_report_view(data: ReportInput, generated_at: datetime) -> ReportView:
    scope: list[ScopeItem] = []
    results: list[FinalResult] = []
    pending: list[PendingItem] = []
    exclusions: list[Exclusion] = []

    for ctrl in data.controls:
        scope.append(ScopeItem(code=ctrl.code, title=ctrl.title))

        if not ctrl.versions:
            pending.append(
                PendingItem(
                    code=ctrl.code,
                    title=ctrl.title,
                    reason="no_result",
                    reason_label=PENDING_REASON_LABELS["no_result"],
                )
            )
            continue

        sorted_versions = sorted(ctrl.versions, key=lambda v: v.version_no)
        highest = sorted_versions[-1]

        if highest.author_actor == "aligo_consultant":
            reviewed_by = highest.author_name or ""
            reviewed_at = highest.created_at

            if highest.control_status == "not_applicable":
                exclusions.append(
                    Exclusion(
                        code=ctrl.code,
                        title=ctrl.title,
                        justification=highest.justification or "",
                        reviewed_by=reviewed_by,
                        reviewed_at=reviewed_at,
                    )
                )
            else:
                results.append(
                    FinalResult(
                        code=ctrl.code,
                        title=ctrl.title,
                        control_status=highest.control_status,
                        status_label=STATUS_LABELS[highest.control_status],
                        basis="consultant_version",
                        reviewed_by=reviewed_by,
                        reviewed_at=reviewed_at,
                        explanation=highest.explanation,
                        not_assessed_reason=highest.not_assessed_reason,
                        evidence=highest.evidence,
                        evidence_pending=highest.evidence_pending,
                    )
                )
        elif highest.author_actor == "agent":
            if highest.review is None:
                pending.append(
                    PendingItem(
                        code=ctrl.code,
                        title=ctrl.title,
                        reason="awaiting_review",
                        reason_label=PENDING_REASON_LABELS["awaiting_review"],
                    )
                )
            elif highest.review.outcome == "accepted":
                reviewed_by = highest.review.reviewer_name
                reviewed_at = highest.review.reviewed_at

                if highest.control_status == "not_applicable":
                    exclusions.append(
                        Exclusion(
                            code=ctrl.code,
                            title=ctrl.title,
                            justification=highest.justification or "",
                            reviewed_by=reviewed_by,
                            reviewed_at=reviewed_at,
                        )
                    )
                else:
                    results.append(
                        FinalResult(
                            code=ctrl.code,
                            title=ctrl.title,
                            control_status=highest.control_status,
                            status_label=STATUS_LABELS[highest.control_status],
                            basis="accepted_agent_result",
                            reviewed_by=reviewed_by,
                            reviewed_at=reviewed_at,
                            explanation=highest.explanation,
                            not_assessed_reason=highest.not_assessed_reason,
                            evidence=highest.evidence,
                            evidence_pending=highest.evidence_pending,
                        )
                    )
            elif highest.review.outcome == "rejected":
                pending.append(
                    PendingItem(
                        code=ctrl.code,
                        title=ctrl.title,
                        reason="rejected_awaiting_new_version",
                        reason_label=PENDING_REASON_LABELS["rejected_awaiting_new_version"],
                    )
                )
            elif highest.review.outcome == "modified":
                pending.append(
                    PendingItem(
                        code=ctrl.code,
                        title=ctrl.title,
                        reason="modified_awaiting_consultant_version",
                        reason_label=PENDING_REASON_LABELS["modified_awaiting_consultant_version"],
                    )
                )

    # Sort all lists by control code
    scope.sort(key=lambda s: s.code)
    results.sort(key=lambda r: r.code)
    pending.sort(key=lambda p: p.code)
    exclusions.sort(key=lambda e: e.code)

    controls_in_scope = len(data.controls)
    finalized = len(results) + len(exclusions)
    pending_count = len(pending)
    final_with_evidence_pending = sum(1 for res in results if res.evidence_pending)
    coverage_pct = round(finalized / controls_in_scope * 100, 1) if controls_in_scope > 0 else 0.0

    status_counts: dict[str, int] = {
        "implemented": 0,
        "partially_implemented": 0,
        "not_implemented": 0,
        "not_assessed": 0,
    }
    for res in results:
        if res.control_status in status_counts:
            status_counts[res.control_status] += 1

    summary = ReportSummary(
        controls_in_scope=controls_in_scope,
        finalized=finalized,
        pending=pending_count,
        final_with_evidence_pending=final_with_evidence_pending,
        coverage_pct=coverage_pct,
        status_counts=status_counts,
    )

    return ReportView(
        organization=data.organization,
        assessment=data.assessment,
        generated_at=generated_at,
        is_demo_data=data.is_demo_data,
        scope=scope,
        results=results,
        pending=pending,
        exclusions=exclusions,
        summary=summary,
    )
