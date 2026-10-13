from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EvidenceFileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    assessment_id: UUID | None
    uploaded_by_user_id: UUID | None
    original_filename: str
    content_type: str | None
    file_extension: str
    size_bytes: int
    sha256: str
    created_at: datetime
