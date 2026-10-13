"""Assessment schemas (AGRC-61)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_KB_VERSION = "demo-0.2"   # the agent's provisional KB (agentic_grc_agent/data/kb_demo.yaml) until E0-03

AssessmentStatus = Literal["draft", "in_progress", "awaiting_review", "completed"]


class AssessmentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)       # strip; blank after strip -> ValueError "This field cannot be blank."
    kb_version: str | None = Field(default=None, min_length=1, max_length=50)  # strip; blank -> same error

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("This field cannot be blank.")
        return stripped

    @field_validator("kb_version")
    @classmethod
    def validate_kb_version(cls, v: str | None) -> str | None:
        if v is None:
            return None
        stripped = v.strip()
        if not stripped:
            raise ValueError("This field cannot be blank.")
        return stripped


class AssessmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    title: str
    framework_code: str
    framework_version: str
    kb_version: str
    status: AssessmentStatus
    created_by_user_id: UUID | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
