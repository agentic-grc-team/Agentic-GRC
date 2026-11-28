from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class TenantSnapshotSummary(BaseModel):
    id: UUID
    organization_id: UUID
    assessment_id: UUID
    collected_by_user_id: UUID | None
    source: str
    tenant_id: str
    schema_version: int
    collected_at: datetime
    reference: str
    # Section name -> "collected" or "not_available" (e.g. a feature the tenant licence lacks).
    sections: dict[str, str]


class TenantSnapshotRead(TenantSnapshotSummary):
    data: dict[str, Any]
