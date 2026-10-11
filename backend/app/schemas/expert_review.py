from typing import Literal

from pydantic import BaseModel


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


class ReviewDecisionResponse(BaseModel):
    result_id: str
    outcome: Literal["accepted", "modified", "rejected"]
    comment: str
    message: str