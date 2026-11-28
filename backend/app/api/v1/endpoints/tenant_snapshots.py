"""Microsoft 365 configuration snapshots of an assessment (AGRC-161)."""

from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_db_session
from app.api.v1.endpoints.assessments import ASSESSMENT_CREATOR_ROLES
from app.api.v1.endpoints.organizations import _active_membership
from app.core.config import Settings, get_settings
from app.db.models import TenantConfigurationSnapshot, User
from app.schemas.tenant_snapshots import TenantSnapshotRead, TenantSnapshotSummary
from app.security.auth import get_current_user
from app.services.assessments import get_assessment
from app.services.m365.graph import M365CollectionError
from app.services.m365.snapshots import (
    M365NotConfigured,
    collect_snapshot,
    get_snapshot,
    list_snapshots,
    snapshot_reference,
)

router = APIRouter(prefix="/organizations", tags=["tenant-snapshots"])


def get_graph_transport() -> httpx.BaseTransport | None:
    """The network by default; tests replace it with sample answers."""
    return None


def _require_consultant(db: Session, organization_id: UUID, assessment_id: UUID, user: User) -> None:
    """Snapshots list the tenant's users and admins, so only administrators and consultants see them."""
    if not user.is_platform_admin:
        membership = _active_membership(db, organization_id, user.id)
        if membership is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found.")
        if membership.role not in ASSESSMENT_CREATOR_ROLES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators and consultants can read Microsoft 365 configuration.",
            )
    if get_assessment(db, organization_id, assessment_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found.")


def _summary_fields(snapshot: TenantConfigurationSnapshot) -> dict:
    sections = (snapshot.data or {}).get("sections", {})
    return {
        "id": snapshot.id,
        "organization_id": snapshot.organization_id,
        "assessment_id": snapshot.assessment_id,
        "collected_by_user_id": snapshot.collected_by_user_id,
        "source": snapshot.source,
        "tenant_id": snapshot.tenant_id,
        "schema_version": snapshot.schema_version,
        "collected_at": snapshot.collected_at,
        "reference": snapshot_reference(snapshot.id),
        "sections": {name: section.get("status", "unknown") for name, section in sections.items()},
    }


def _read(snapshot: TenantConfigurationSnapshot) -> TenantSnapshotRead:
    return TenantSnapshotRead(**_summary_fields(snapshot), data=snapshot.data)


@router.post(
    "/{organization_id}/assessments/{assessment_id}/tenant-snapshots",
    response_model=TenantSnapshotRead,
    status_code=status.HTTP_201_CREATED,
)
def create_tenant_snapshot(
    organization_id: UUID,
    assessment_id: UUID,
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    transport: httpx.BaseTransport | None = Depends(get_graph_transport),
) -> TenantSnapshotRead:
    """Read the Microsoft 365 tenant now and store a dated snapshot for this assessment.

    The read is all or nothing: on a connection, sign-in or permission failure the answer is 502 with
    the reason, and no snapshot is stored.
    """
    _require_consultant(db, organization_id, assessment_id, user)
    try:
        snapshot = collect_snapshot(db, settings, organization_id, assessment_id, user.id, transport=transport)
    except M365NotConfigured as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except M365CollectionError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=error.message) from error
    return _read(snapshot)


@router.get(
    "/{organization_id}/assessments/{assessment_id}/tenant-snapshots",
    response_model=list[TenantSnapshotSummary],
)
def read_tenant_snapshots(
    organization_id: UUID,
    assessment_id: UUID,
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> list[TenantSnapshotSummary]:
    _require_consultant(db, organization_id, assessment_id, user)
    return [
        TenantSnapshotSummary(**_summary_fields(snapshot))
        for snapshot in list_snapshots(db, organization_id, assessment_id)
    ]


@router.get(
    "/{organization_id}/assessments/{assessment_id}/tenant-snapshots/{snapshot_id}",
    response_model=TenantSnapshotRead,
)
def read_tenant_snapshot(
    organization_id: UUID,
    assessment_id: UUID,
    snapshot_id: UUID,
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> TenantSnapshotRead:
    _require_consultant(db, organization_id, assessment_id, user)
    snapshot = get_snapshot(db, organization_id, assessment_id, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot not found.")
    return _read(snapshot)
