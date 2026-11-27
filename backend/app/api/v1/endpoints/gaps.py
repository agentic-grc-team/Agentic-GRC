from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_db_session
from app.api.v1.report_access import load_report_input
from app.db.models import Assessment, User
from app.schemas.gaps import GapAnalysisRunRead, GapList
from app.security.auth import get_current_user
from app.security.expert_reviews import require_expert_review_access
from app.services.gaps import build_gap_list
from app.services.gap_analysis_runs import list_gap_analysis_runs, record_gap_analysis_run, run_gap_list
from app.services.reports.source import ReportDataSource, get_report_source

router = APIRouter(prefix="/organizations", tags=["gaps"])


@router.get(
    "/{organization_id}/assessments/{assessment_id}/gaps",
    response_model=GapList,
)
def get_gap_list_endpoint(
    organization_id: UUID,
    assessment_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    source: ReportDataSource = Depends(get_report_source),
) -> GapList:
    # Same access rule and data as the report: active members of the organization and platform admins.
    data = load_report_input(organization_id, assessment_id, user, db, source)
    return build_gap_list(data, datetime.now(timezone.utc))


def _read_run(row) -> GapAnalysisRunRead:
    return GapAnalysisRunRead(
        id=row.id,
        organization_id=row.organization_id,
        assessment_id=row.assessment_id,
        trigger=row.trigger,
        requested_by_user_id=row.requested_by_user_id,
        created_at=row.created_at,
        gap_count=row.gap_count,
        gap_list=run_gap_list(row),
    )


@router.get(
    "/{organization_id}/assessments/{assessment_id}/gaps/runs",
    response_model=list[GapAnalysisRunRead],
)
def get_gap_analysis_runs(
    organization_id: UUID,
    assessment_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    source: ReportDataSource = Depends(get_report_source),
) -> list[GapAnalysisRunRead]:
    load_report_input(organization_id, assessment_id, user, db, source)
    return [_read_run(run) for run in list_gap_analysis_runs(db, organization_id, assessment_id)]


@router.post(
    "/{organization_id}/assessments/{assessment_id}/gaps/regenerate",
    response_model=GapAnalysisRunRead,
    status_code=status.HTTP_201_CREATED,
)
def regenerate_gap_analysis(
    organization_id: UUID,
    assessment_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> GapAnalysisRunRead:
    require_expert_review_access(db, organization_id, user)
    assessment = db.scalar(
        select(Assessment)
        .where(Assessment.organization_id == organization_id, Assessment.id == assessment_id)
        .with_for_update()
    )
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found.")
    if assessment.status != "completed":
        raise HTTPException(status_code=409, detail="Complete the assessment before regenerating its gaps.")
    run = record_gap_analysis_run(
        db, organization_id, assessment_id, trigger="regeneration", requested_by_user_id=user.id
    )
    response = _read_run(run)
    db.commit()
    return response
