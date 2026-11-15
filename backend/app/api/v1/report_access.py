from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.api.v1.endpoints.organizations import _active_membership
from app.db.models import User
from app.schemas.report import ReportInput
from app.services.reports.source import ReportDataSource


def load_report_input(
    organization_id: UUID,
    assessment_id: UUID,
    user: User,
    db: Session,
    source: ReportDataSource,
) -> ReportInput:
    """The report data of an assessment, for active members of its organization and platform admins.

    Shared by the report and gap list endpoints so both apply the same access rule. Anyone else gets
    the same 404 as an unknown assessment, so no data is disclosed.
    """
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
