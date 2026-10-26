"""Assessment schemas (AGRC-61, AGRC-63)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.assessment_scope import KB_SCOPES

DEFAULT_KB_VERSION = "demo-0.2"   # the agent's provisional KB (app/agent/data/kb_demo.yaml) until E0-03

AssessmentStatus = Literal["draft", "in_progress", "awaiting_review", "completed"]


class AssessmentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)       # strip; blank after strip -> ValueError "This field cannot be blank."
    kb_version: str | None = Field(default=None, min_length=1, max_length=50)  # strip; blank -> same error; unknown version -> ValueError

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
        # An unknown version would create an assessment without controls (AGRC-73).
        if stripped not in KB_SCOPES:
            supported = ", ".join(KB_SCOPES)
            raise ValueError(f"Unknown knowledge-base version. Supported versions: {supported}.")
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


class ScopeControlRead(BaseModel):
    code: str
    title: str


class ScopeCategoryRead(BaseModel):
    code: str
    name: str | None  # None only for a category missing from the CSF 2.0 catalog
    controls: list[ScopeControlRead]


class ScopeFunctionRead(BaseModel):
    code: str
    name: str
    categories: list[ScopeCategoryRead]


class AssessmentScopeRead(BaseModel):
    """What an assessment covers, shown before the interview starts (HU-04, AGRC-63)."""

    organization_id: UUID
    organization_name: str
    assessment: AssessmentRead
    control_count: int
    functions: list[ScopeFunctionRead]
