"""REST contracts for authenticated assessment interviews."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


InterviewSessionType = Literal["kickoff", "block", "recovery", "evidence_review"]


class InterviewSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_type: InterviewSessionType = "kickoff"
    block_id: UUID | None = None
    restart: bool = Field(
        default=False,
        description="End the active session and start a new one, preserving the old transcript.",
    )

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
    replies_to_turn_id: UUID
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
        normalized = value.replace("_", "-")
        if normalized.lower() != "en" and not normalized.lower().startswith("en-"):
            raise ValueError("The configured interview agent currently supports English only.")
        return normalized


class InterviewControlRead(BaseModel):
    id: UUID
    code: str
    title: str


class InterviewDraftResultRead(BaseModel):
    id: UUID
    assessment_control_id: UUID
    control_code: str
    control_title: str
    status: Literal[
        "implemented",
        "partially_implemented",
        "not_implemented",
        "not_applicable",
        "not_assessed",
    ]
    explanation: str
    justification: str | None
    not_assessed_reason: str | None
    confidence: float | None
    requires_human_review: bool
    evidence_pending: bool
    evidence_summary: str | None
    evidence_refs: list[dict[str, Any]]
    trace_id: UUID | None
    created_at: datetime


class InterviewSourceReference(BaseModel):
    type: Literal["interview_turn"]
    ref: str


class InterviewSessionRead(BaseModel):
    id: UUID
    session_type: InterviewSessionType
    block_id: UUID | None
    closed: bool
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
    draft_results: list[InterviewDraftResultRead] = Field(default_factory=list)
    resumed: bool = False


class InterviewTurnReceipt(BaseModel):
    turn: InterviewTurnRead
    agent_turns: list[InterviewTurnRead] = Field(default_factory=list)
    draft_results: list[InterviewDraftResultRead] = Field(default_factory=list)
    session_closed: bool = False
    idempotent_replay: bool = False
