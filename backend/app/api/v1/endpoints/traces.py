"""Read and export reasoning traces (AGRC-15 / AGRC-26)."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_db_session
from app.api.v1.endpoints.organizations import _active_membership
from app.db.models import User
from app.schemas.decision_trace import DecisionTraceExport, DecisionTraceRead
from app.security.auth import get_current_user
from app.services.decision_traces import list_traces


router = APIRouter(prefix="/organizations", tags=["decision traces"])

# HU-03: the organization representative must not see the agent's internal traces.
TRACE_READER_ROLES = ("administrator", "consultant")


def _require_trace_access(db: Session, organization_id: UUID, user: User) -> None:
    if user.is_platform_admin:
        return
    membership = _active_membership(db, organization_id, user.id)
    if membership is None:
        # Same answer as for an organization that does not exist, so nothing leaks.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")
    if membership.role not in TRACE_READER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators and consultants can view decision traces.",
        )


@router.get(
    "/{organization_id}/assessments/{assessment_id}/traces",
    response_model=list[DecisionTraceRead],
)
def get_traces(
    organization_id: UUID,
    assessment_id: UUID,
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> list[DecisionTraceRead]:
    _require_trace_access(db, organization_id, user)
    records = list_traces(db, organization_id, assessment_id)
    return [DecisionTraceRead.model_validate(record) for record in records]


@router.get("/{organization_id}/assessments/{assessment_id}/traces/export")
def export_traces(
    organization_id: UUID,
    assessment_id: UUID,
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> JSONResponse:
    _require_trace_access(db, organization_id, user)
    records = list_traces(db, organization_id, assessment_id)
    export = DecisionTraceExport(
        organization_id=organization_id,
        assessment_id=assessment_id,
        exported_at=datetime.now(timezone.utc),
        trace_count=len(records),
        traces=[DecisionTraceRead.model_validate(record) for record in records],
    )
    return JSONResponse(
        content=export.model_dump(mode="json"),
        headers={"Content-Disposition": f'attachment; filename="traces-{assessment_id}.json"'},
    )
