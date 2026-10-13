from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_db_session
from app.api.v1.endpoints.organizations import _active_membership
from app.db.models import User
from app.schemas.report import ReportInput, ReportView
from app.security.auth import get_current_user
from app.services.reports.builder import build_report_view
from app.services.reports.pdf import render_report_pdf
from app.services.reports.source import ReportDataSource, get_report_source

router = APIRouter(prefix="/organizations", tags=["reports"])


def _load_report_input(
    organization_id: UUID,
    assessment_id: UUID,
    user: User,
    db: Session,
    source: ReportDataSource,
) -> ReportInput:
    is_admin = getattr(user, "is_platform_admin", False)
    membership = _active_membership(db, organization_id, user.id) if not is_admin else None

    if not is_admin and membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment not found.",
        )

    data = source.load(db, organization_id, assessment_id)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment not found.",
        )

    return data


@router.get(
    "/{organization_id}/assessments/{assessment_id}/report",
    response_model=ReportView,
)
def get_report_view_endpoint(
    organization_id: UUID,
    assessment_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    source: ReportDataSource = Depends(get_report_source),
) -> ReportView:
    data = _load_report_input(organization_id, assessment_id, user, db, source)
    generated_at = datetime.now(timezone.utc)
    return build_report_view(data, generated_at)


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
    data = _load_report_input(organization_id, assessment_id, user, db, source)
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
