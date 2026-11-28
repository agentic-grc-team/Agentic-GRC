"""Collect and store Microsoft 365 configuration snapshots (AGRC-161)."""

from __future__ import annotations

from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import TenantConfigurationSnapshot
from app.services.m365.graph import GraphCredentials, GraphTenantReader
from app.services.m365.sample import SAMPLE_TENANT_ID, sample_transport


class M365NotConfigured(Exception):
    """Collection is turned off, or this organization is not the one linked to the tenant."""


def snapshot_reference(snapshot_id: UUID, path: str = "") -> str:
    """Trace source reference for a snapshot, as in docs/design/trace-schema.md."""
    return f"tenant_configuration:{snapshot_id}/{path.lstrip('/')}"


def _reader(settings: Settings, organization_id: UUID, transport: httpx.BaseTransport | None):
    mode = settings.ms365_data_mode
    if mode == "disabled":
        raise M365NotConfigured("Microsoft 365 collection is turned off (MS365_DATA_MODE=disabled).")
    if mode == "sample":
        credentials = GraphCredentials(SAMPLE_TENANT_ID, "sample-client", "sample-secret")
        return "sample", GraphTenantReader(
            credentials, transport=transport or sample_transport(), timeout_seconds=settings.ms365_timeout_seconds
        )
    if settings.ms365_organization_id != organization_id:
        raise M365NotConfigured("This organization is not linked to the configured Microsoft 365 tenant.")
    credentials = GraphCredentials(
        settings.ms365_tenant_id or "",
        settings.ms365_client_id or "",
        settings.ms365_client_secret.get_secret_value() if settings.ms365_client_secret else "",
    )
    return "microsoft_graph", GraphTenantReader(
        credentials, transport=transport, timeout_seconds=settings.ms365_timeout_seconds
    )


def collect_snapshot(
    db: Session,
    settings: Settings,
    organization_id: UUID,
    assessment_id: UUID,
    user_id: UUID | None,
    *,
    transport: httpx.BaseTransport | None = None,
) -> TenantConfigurationSnapshot:
    """Read the tenant and store one snapshot. Raises before writing anything if the read fails."""
    source, reader = _reader(settings, organization_id, transport)
    with reader:
        data = reader.collect()  # M365CollectionError propagates; nothing has been written yet
    snapshot = TenantConfigurationSnapshot(
        organization_id=organization_id,
        assessment_id=assessment_id,
        collected_by_user_id=user_id,
        source=source,
        tenant_id=str(data["tenant"]["id"]),
        schema_version=data["schema_version"],
        data=data,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def list_snapshots(db: Session, organization_id: UUID, assessment_id: UUID) -> list[TenantConfigurationSnapshot]:
    """Snapshots of one assessment, newest first. Always filtered by organization."""
    return list(
        db.scalars(
            select(TenantConfigurationSnapshot)
            .where(
                TenantConfigurationSnapshot.organization_id == organization_id,
                TenantConfigurationSnapshot.assessment_id == assessment_id,
            )
            .order_by(TenantConfigurationSnapshot.collected_at.desc(), TenantConfigurationSnapshot.id)
        )
    )


def get_snapshot(
    db: Session, organization_id: UUID, assessment_id: UUID, snapshot_id: UUID
) -> TenantConfigurationSnapshot | None:
    return db.scalars(
        select(TenantConfigurationSnapshot).where(
            TenantConfigurationSnapshot.organization_id == organization_id,
            TenantConfigurationSnapshot.assessment_id == assessment_id,
            TenantConfigurationSnapshot.id == snapshot_id,
        )
    ).first()
