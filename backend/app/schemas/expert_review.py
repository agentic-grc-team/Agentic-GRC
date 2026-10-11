from typing import Literal

from pydantic import BaseModel, field_validator, model_validator


class ReviewItem(BaseModel):
    result_id: str
    assessment_id: str
    control_code: str
    control_title: str
    control_status: str
    maturity_current: int
    confidence: float
    explanation: str
    evidence_summary: str
    requires_human_review: bool


class ReviewDecision(BaseModel):
    outcome: Literal["accepted", "modified", "rejected"]
    comment: str = ""

    @field_validator("comment")
    @classmethod
    def trim_comment(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def require_comment_for_modified_or_rejected(self):
        if self.outcome in ("modified", "rejected") and not self.comment:
            raise ValueError(
                "A review comment is required when modifying or rejecting a result."
            )

        return self


class ReviewDecisionResponse(BaseModel):
    result_id: str
    outcome: Literal["accepted", "modified", "rejected"]
    comment: str
    message: str