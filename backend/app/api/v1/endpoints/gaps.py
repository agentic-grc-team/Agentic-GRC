from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_db_session
from app.api.v1.report_access import load_report_input
from app.db.models import User
from app.schemas.gaps import GapList
from app.security.auth import get_current_user
from app.services.gaps import build_gap_list
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
