from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

ControlStatus = Literal[
    "implemented",
    "partially_implemented",
    "not_implemented",
    "not_assessed",
    "not_applicable",
]
AuthorActor = Literal["agent", "aligo_consultant"]
ReviewOutcome = Literal["accepted", "modified", "rejected"]
AssessmentStatus = Literal["draft", "in_progress", "awaiting_review", "completed"]
EvidenceSourceType = Literal[
    "interview_turn", "document_span", "tenant_configuration", "prior_phase_evidence"
]
EvidenceNature = Literal["intent", "implementation", "attestation"]

STATUS_LABELS: dict[str, str] = {
    "implemented": "Implemented",
    "partially_implemented": "Partially implemented",
    "not_implemented": "Not implemented",
    "not_assessed": "Not assessed",
    "not_applicable": "Not applicable",
}

PENDING_REASON_LABELS: dict[str, str] = {
    "awaiting_review": "Awaiting expert review",
    "rejected_awaiting_new_version": "Rejected by reviewer — new assessment required",
    "no_result": "Not yet assessed",
}


class OrganizationInfo(BaseModel):
    id: UUID
    name: str
    sector: str  # human label, e.g. "Financial services"
    size: str  # human label, e.g. "51-250 employees"


class AssessmentInfo(BaseModel):
    id: UUID
    title: str
    framework: str = "NIST CSF 2.0"
    kb_version: str
    status: AssessmentStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None


class EvidenceReference(BaseModel):
    source_type: EvidenceSourceType
    reference: str  # e.g. "Access Control Policy v2.pdf, p. 4, §3.2"
    excerpt: str | None = None  # short quoted text, max 300 chars
    nature: EvidenceNature

    @field_validator("excerpt")
    @classmethod
    def validate_excerpt(cls, v: str | None) -> str | None:
        if v is not None and len(v) > 300:
            raise ValueError("Excerpt must not exceed 300 characters")
        return v


class ResultReview(BaseModel):
    outcome: ReviewOutcome
    reviewer_name: str
    reviewed_at: datetime
    comment: str = ""


class ResultVersion(BaseModel):
    """One immutable version of the result for one control (mirrors control_results in schema v0.3)."""

    version_no: int = Field(ge=1)
    author_actor: AuthorActor
    author_name: str | None = None  # required when author_actor == "aligo_consultant"
    control_status: ControlStatus
    explanation: str
    justification: str | None = None  # required (non-blank) when control_status == "not_applicable"
    not_assessed_reason: str | None = None  # required (non-blank) when control_status == "not_assessed"
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence: list[EvidenceReference] = []
    evidence_pending: bool = False  # True = status rests on an attestation not yet validated
    created_at: datetime
    review: ResultReview | None = None  # only meaningful for agent versions

    @model_validator(mode="after")
    def validate_version_constraints(self) -> "ResultVersion":
        if self.author_actor == "aligo_consultant":
            if not self.author_name or not self.author_name.strip():
                raise ValueError("author_name is required and must not be blank when author_actor is aligo_consultant")

        if self.control_status == "not_applicable":
            if not self.justification or not self.justification.strip():
                raise ValueError("justification is required and must not be blank when control_status is not_applicable")

        if self.control_status == "not_assessed":
            if not self.not_assessed_reason or not self.not_assessed_reason.strip():
                raise ValueError("not_assessed_reason is required and must not be blank when control_status is not_assessed")

        if self.review is not None and self.author_actor != "agent":
            raise ValueError("review is only allowed when author_actor is agent")

        return self


class ControlInScope(BaseModel):
    code: str = Field(pattern=r"^(GV|ID|PR|DE|RS|RC)\.[A-Z]{2}-\d{2}$")
    title: str
    versions: list[ResultVersion] = []  # any order; builder sorts by version_no


class ReportInput(BaseModel):
    organization: OrganizationInfo
    assessment: AssessmentInfo
    controls: list[ControlInScope]
    is_demo_data: bool = False


FinalBasis = Literal["accepted_agent_result", "consultant_version"]
PendingReason = Literal["awaiting_review", "rejected_awaiting_new_version", "no_result"]


class FinalResult(BaseModel):
    code: str
    title: str
    control_status: ControlStatus
    status_label: str  # from STATUS_LABELS
    basis: FinalBasis
    reviewed_by: str  # reviewer_name (accepted) or author_name (consultant version)
    reviewed_at: datetime  # review.reviewed_at or version.created_at
    explanation: str
    not_assessed_reason: str | None = None
    evidence: list[EvidenceReference] = []
    evidence_pending: bool = False


class PendingItem(BaseModel):
    code: str
    title: str
    reason: PendingReason
    reason_label: str  # see 5.3


class Exclusion(BaseModel):
    code: str
    title: str
    justification: str
    reviewed_by: str
    reviewed_at: datetime


class ReportSummary(BaseModel):
    controls_in_scope: int
    finalized: int  # final results + exclusions
    pending: int
    coverage_pct: float  # finalized / controls_in_scope * 100, rounded to 1 decimal; 0.0 if no controls
    status_counts: dict[str, int]  # keys: implemented, partially_implemented, not_implemented, not_assessed (always all 4, zero if none). Excludes not_applicable.


class ScopeItem(BaseModel):
    code: str
    title: str


class ReportView(BaseModel):
    organization: OrganizationInfo
    assessment: AssessmentInfo
    generated_at: datetime
    is_demo_data: bool
    scope: list[ScopeItem]  # code + title only, sorted by code. Never include versions (drafts must not leak).
    results: list[FinalResult]  # sorted by control code
    pending: list[PendingItem]  # sorted by control code
    exclusions: list[Exclusion]  # sorted by control code
    summary: ReportSummary
