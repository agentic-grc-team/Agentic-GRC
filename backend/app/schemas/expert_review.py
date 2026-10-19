from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.evidence import EvidenceFileRead


ControlStatus = Literal[
    "implemented",
    "partially_implemented",
    "not_implemented",
    "not_applicable",
    "not_assessed",
]


class ReviewItem(BaseModel):
    result_id: str
    assessment_id: str
    control_code: str
    control_title: str
    control_status: str
    maturity_current: int | None = None
    confidence: float | None = None
    explanation: str
    evidence_summary: str
    requires_human_review: bool
    justification: str | None = None
    not_assessed_reason: str | None = None

class ReviewEvidenceSource(BaseModel):
    source_type: Literal["document_span", "interview_turn", "other"]
    reference: str
    excerpt: str | None = None
    document: EvidenceFileRead | None = None


class ReviewEvidence(BaseModel):
    result_id: str
    evidence_pending: bool
    sources: list[ReviewEvidenceSource] = Field(default_factory=list)
    linked_documents: list[EvidenceFileRead] = Field(default_factory=list)
    skipped_source_count: int = 0

class ModifiedResult(BaseModel):
    control_status: ControlStatus
    explanation: str
    justification: str | None = None
    not_assessed_reason: str | None = None

    @field_validator(
        "explanation",
        "justification",
        "not_assessed_reason",
    )
    @classmethod
    def trim_text(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return value.strip()

    @model_validator(mode="after")
    def validate_modified_result(self):
        if not self.explanation:
            raise ValueError(
                "An explanation is required for a modified result."
            )

        if (
            self.control_status == "not_applicable"
            and not self.justification
        ):
            raise ValueError(
                "A justification is required for not_applicable."
            )

        if (
            self.control_status == "not_assessed"
            and not self.not_assessed_reason
        ):
            raise ValueError(
                "A reason is required for not_assessed."
            )

        return self


class ReviewDecision(BaseModel):
    outcome: Literal["accepted", "modified", "rejected"]
    comment: str = ""
    modified_result: ModifiedResult | None = None

    @field_validator("comment")
    @classmethod
    def trim_comment(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_decision(self):
        if self.outcome in ("modified", "rejected") and not self.comment:
            raise ValueError(
                "A review comment is required when modifying or rejecting a result."
            )

        if self.outcome == "modified":
            if self.modified_result is None:
                raise ValueError(
                    "A modified result is required for a modified decision."
                )
        elif self.modified_result is not None:
            raise ValueError(
                "Only a modified decision can include a modified result."
            )

        return self


class ReviewDecisionResponse(BaseModel):
    result_id: str
    outcome: Literal["accepted", "modified", "rejected"]
    comment: str
    message: str