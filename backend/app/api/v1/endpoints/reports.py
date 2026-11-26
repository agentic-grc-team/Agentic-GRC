from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_db_session
from app.api.v1.report_access import load_report_input
from app.db.models import User
from app.schemas.gaps import ReportPreview
from app.schemas.report import (
    AssessmentComparison,
    ComparisonCandidate,
    ReportExport,
    ReportView,
)
from app.security.auth import get_current_user
from app.services.gaps import build_gap_list
from app.services.reports.builder import build_report_view
from app.services.reports.comparison import build_comparison, list_comparison_candidates
from app.services.reports.pdf import render_report_pdf
from app.services.reports.source import ReportDataSource, get_report_source

router = APIRouter(prefix="/organizations", tags=["reports"])

COMPARE_WITH_QUERY = Query(
    default=None,
    description="Id of an earlier completed assessment of the same organization to compare with.",
)


def _comparison_for(
    organization_id: UUID,
    current: ReportView,
    previous_id: UUID,
    user: User,
    db: Session,
    source: ReportDataSource,
    generated_at: datetime,
) -> AssessmentComparison:
    """Compare the current report data with an eligible earlier assessment (HU-24).

    The previous assessment must be an earlier completed assessment of the same organization.
    Anything else (another organization, not completed, later, unknown) gets the same 404, so no
    data about other assessments is disclosed.
    """
    candidate_ids = {
        candidate.id
        for candidate in list_comparison_candidates(db, organization_id, current.assessment.id)
    }
    if previous_id not in candidate_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No earlier completed assessment of this organization with that id.",
        )
    previous = load_report_input(organization_id, previous_id, user, db, source)
    return build_comparison(current, build_report_view(previous, generated_at))


@router.get(
    "/{organization_id}/assessments/{assessment_id}/report",
    response_model=ReportPreview,
)
def get_report_view_endpoint(
    organization_id: UUID,
    assessment_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    source: ReportDataSource = Depends(get_report_source),
) -> ReportPreview:
    data = load_report_input(organization_id, assessment_id, user, db, source)
    generated_at = datetime.now(timezone.utc)
    view = build_report_view(data, generated_at)
    # The preview carries the gap list (HU-17) built from this same view, so the page never shows a
    # gap list and a report that disagree.
    return ReportPreview(
        **view.model_dump(), gap_list=build_gap_list(data, generated_at, view=view)
    )


@router.get(
    "/{organization_id}/assessments/{assessment_id}/report.pdf",
    response_class=Response,
)
def get_report_pdf_endpoint(
    organization_id: UUID,
    assessment_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    source: ReportDataSource = Depends(get_report_source),
    compare_with: UUID | None = COMPARE_WITH_QUERY,
) -> Response:
    data = load_report_input(organization_id, assessment_id, user, db, source)
    generated_at = datetime.now(timezone.utc)
    view = build_report_view(data, generated_at)
    comparison = (
        _comparison_for(organization_id, view, compare_with, user, db, source, generated_at)
        if compare_with is not None
        else None
    )
    pdf_bytes = render_report_pdf(view, comparison=comparison)

    headers = {
        "Content-Disposition": f'attachment; filename="agentic-grc-report-{assessment_id}.pdf"'
    }
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers=headers,
    )


@router.get(
    "/{organization_id}/assessments/{assessment_id}/report.json",
    response_class=Response,
)
def get_report_json_endpoint(
    organization_id: UUID,
    assessment_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    source: ReportDataSource = Depends(get_report_source),
    compare_with: UUID | None = COMPARE_WITH_QUERY,
) -> Response:
    data = load_report_input(organization_id, assessment_id, user, db, source)
    generated_at = datetime.now(timezone.utc)
    view = build_report_view(data, generated_at)
    comparison = (
        _comparison_for(organization_id, view, compare_with, user, db, source, generated_at)
        if compare_with is not None
        else None
    )
    export = ReportExport(report=view, comparison=comparison)

    headers = {
        "Content-Disposition": f'attachment; filename="agentic-grc-report-{assessment_id}.json"'
    }
    return Response(
        content=export.model_dump_json(indent=2),
        media_type="application/json",
        headers=headers,
    )


@router.get(
    "/{organization_id}/assessments/{assessment_id}/comparison/candidates",
    response_model=list[ComparisonCandidate],
)
def get_comparison_candidates_endpoint(
    organization_id: UUID,
    assessment_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    source: ReportDataSource = Depends(get_report_source),
) -> list[ComparisonCandidate]:
    """Earlier completed assessments of the same organization that this one can be compared with.

    An empty list means there is nothing to compare with yet (the UI shows an empty state).
    """
    # Same access rule as the report: non-members and unknown assessments get 404.
    load_report_input(organization_id, assessment_id, user, db, source)
    return list_comparison_candidates(db, organization_id, assessment_id)


@router.get(
    "/{organization_id}/assessments/{assessment_id}/comparison",
    response_model=AssessmentComparison,
)
def get_comparison_endpoint(
    organization_id: UUID,
    assessment_id: UUID,
    previous: UUID = Query(description="Id of an earlier completed assessment to compare with."),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    source: ReportDataSource = Depends(get_report_source),
) -> AssessmentComparison:
    data = load_report_input(organization_id, assessment_id, user, db, source)
    generated_at = datetime.now(timezone.utc)
    view = build_report_view(data, generated_at)
    return _comparison_for(organization_id, view, previous, user, db, source, generated_at)
