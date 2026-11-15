from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_db_session
from app.api.v1.report_access import load_report_input
from app.db.models import User
from app.schemas.gaps import ReportPreview
from app.schemas.report import ReportExport
from app.security.auth import get_current_user
from app.services.gaps import build_gap_list
from app.services.reports.builder import build_report_view
from app.services.reports.pdf import render_report_pdf
from app.services.reports.source import ReportDataSource, get_report_source

router = APIRouter(prefix="/organizations", tags=["reports"])


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
) -> Response:
    data = load_report_input(organization_id, assessment_id, user, db, source)
    generated_at = datetime.now(timezone.utc)
    view = build_report_view(data, generated_at)
    pdf_bytes = render_report_pdf(view)

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
) -> Response:
    data = load_report_input(organization_id, assessment_id, user, db, source)
    generated_at = datetime.now(timezone.utc)
    view = build_report_view(data, generated_at)
    export = ReportExport(report=view)

    headers = {
        "Content-Disposition": f'attachment; filename="agentic-grc-report-{assessment_id}.json"'
    }
    return Response(
        content=export.model_dump_json(indent=2),
        media_type="application/json",
        headers=headers,
    )
