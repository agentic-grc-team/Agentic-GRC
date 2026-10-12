"""Reasoning trace record (AGRC-15). Fields and rules follow docs/design/trace-schema.md v0.2."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


DecisionType = Literal[
    "answer_interpreted",
    "evidence_requested",
    "evidence_extracted",
    "evidence_validated",
    "mapping_assigned",
    "status_assessed",
    "maturity_assessed",
    "contradiction_detected",
    "finding_generated",
    "human_review",
]
ActorType = Literal["agent", "assessed_org_representative", "aligo_consultant"]
SourceType = Literal["interview_turn", "document_span", "tenant_configuration", "prior_phase_evidence"]
EvidenceNature = Literal["intent", "implementation", "attestation"]
ReviewOutcome = Literal["accepted", "modified", "rejected"]
CONTROL_STATUSES = ("implemented", "partially_implemented", "not_implemented", "not_applicable", "not_assessed")


class TraceSource(BaseModel):
    type: SourceType
    ref: str = Field(min_length=1)
    excerpt: str | None = None


class DecisionTrace(BaseModel):
    # A. Where
    organization_id: UUID
    assessment_id: UUID

    # B. What was decided
    decision_type: DecisionType
    control_ids: list[str] = []
    module: str | None = None

    # C. Based on what
    sources: list[TraceSource] = []
    evidence_nature: EvidenceNature | None = None

    # D. Who decided and how
    actor_type: ActorType
    actor_user_id: UUID | None = None
    model_name: str | None = None
    prompt_id: str | None = None
    prompt_version: str | None = None
    kb_version: str = Field(min_length=1)

    # E. Result
    output: dict
    rationale: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    requires_human_review: bool = False
    latency_ms: int | None = Field(default=None, ge=0)
    fallback_used: bool = False

    # F. Review and history
    reviews_trace_id: UUID | None = None
    review_outcome: ReviewOutcome | None = None
    supersedes_trace_id: UUID | None = None

    @model_validator(mode="after")
    def check_agent_decision(self) -> "DecisionTrace":
        if self.actor_type != "agent":
            return self
        if not self.prompt_id or not self.prompt_version:
            raise ValueError("An agent decision must record prompt_id and prompt_version.")
        if not self.sources:
            raise ValueError("An agent decision must cite at least one source.")
        is_rule = self.prompt_id.startswith("rule:")
        if not is_rule and not self.model_name:
            raise ValueError("An LLM decision must record model_name.")
        return self

    @model_validator(mode="after")
    def check_human_decision(self) -> "DecisionTrace":
        if self.actor_type == "agent":
            if self.actor_user_id is not None:
                raise ValueError("An agent decision has no actor_user_id.")
            return self
        if self.actor_user_id is None:
            raise ValueError("A human decision must record actor_user_id.")
        if self.confidence is not None:
            raise ValueError("A human decision has no confidence value.")
        return self

    @model_validator(mode="after")
    def check_review(self) -> "DecisionTrace":
        if self.decision_type == "human_review":
            if self.actor_type == "agent":
                raise ValueError("A review must be made by a person, never by the agent.")
            if self.reviews_trace_id is None or self.review_outcome is None:
                raise ValueError("A review must set reviews_trace_id and review_outcome.")
        elif self.reviews_trace_id is not None or self.review_outcome is not None:
            raise ValueError("Only a human_review decision can set reviews_trace_id or review_outcome.")
        return self

    @model_validator(mode="after")
    def check_control_status(self) -> "DecisionTrace":
        if self.decision_type == "status_assessed" and self.output.get("status") not in CONTROL_STATUSES:
            raise ValueError("A status_assessed decision must set output.status to one of: " + ", ".join(CONTROL_STATUSES) + ".")
        return self

    @model_validator(mode="after")
    def check_human_review_flag(self) -> "DecisionTrace":
        # A fallback that only leads to a follow-up question needs no review; a control closed on it does.
        if self.decision_type == "status_assessed" and self.fallback_used and not self.requires_human_review:
            raise ValueError("A control closed on a fallback interpretation must require human review.")
        insufficient = (
            self.decision_type == "evidence_validated"
            and self.output.get("state") == "provided_insufficient"
        )
        if insufficient and not self.requires_human_review:
            raise ValueError("Insufficient evidence must require human review.")
        return self


class DecisionTraceRead(DecisionTrace):
    """A stored trace, as returned by the API. id and created_at come from the database."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


class DecisionTraceExport(BaseModel):
    schema_version: str = "0.2"
    organization_id: UUID
    assessment_id: UUID
    exported_at: datetime
    trace_count: int
    traces: list[DecisionTraceRead]
