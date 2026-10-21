"""REST contracts for authenticated assessment interviews."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


InterviewSessionType = Literal["kickoff", "block", "recovery", "evidence_review"]


class InterviewSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_type: InterviewSessionType = "kickoff"
    block_id: UUID | None = None

    @model_validator(mode="after")
    def check_block(self) -> "InterviewSessionCreate":
        if (self.session_type == "block") != (self.block_id is not None):
            raise ValueError("block_id is required only for a block interview session.")
        return self


class InterviewTurnCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    content: str = Field(min_length=1, max_length=10_000)
    question_id: UUID | None = None
    replies_to_turn_id: UUID | None = None
    language_code: str | None = Field(default=None, max_length=10)
    client_request_id: UUID | None = Field(
        default=None,
        description="Required unless the Idempotency-Key request header is supplied.",
    )

    @field_validator("content")
    @classmethod
    def trim_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("An interview answer cannot be blank.")
        return value

    @field_validator("language_code")
    @classmethod
    def normalize_language_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("language_code cannot be blank.")
        return value


class InterviewControlRead(BaseModel):
    id: UUID
    code: str
    title: str


class InterviewSourceReference(BaseModel):
    type: Literal["interview_turn"]
    ref: str


class InterviewSessionRead(BaseModel):
    id: UUID
    session_type: InterviewSessionType
    block_id: UUID | None
    facilitator_user_id: UUID | None
    scheduled_at: datetime | None
    started_at: datetime | None
    ended_at: datetime | None
    resume_summary: str | None


class InterviewTurnRead(BaseModel):
    id: UUID
    sequence_no: int
    speaker: Literal["agent", "participant"]
    participant_id: UUID | None
    turn_type: Literal[
        "question",
        "answer",
        "follow_up",
        "clarification",
        "evidence_request",
        "contradiction_prompt",
        "summary",
    ]
    question_id: UUID | None
    replies_to_turn_id: UUID | None
    content: str
    language_code: str | None
    created_at: datetime
    source_references: list[InterviewSourceReference] = Field(default_factory=list)


class InterviewRead(BaseModel):
    organization_id: UUID
    organization_name: str
    assessment_id: UUID
    assessment_title: str
    assessment_status: str
    kb_version: str
    participant_id: UUID | None
    session: InterviewSessionRead | None
    turns: list[InterviewTurnRead] = Field(default_factory=list)
    in_scope_controls: list[InterviewControlRead] = Field(default_factory=list)
    resumed: bool = False


class InterviewTurnReceipt(BaseModel):
    turn: InterviewTurnRead
    idempotent_replay: bool = False
