"""The reasoning trace behind one result in Expert reviews (HU-25, AGRC-60)."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.decision_trace import DecisionTraceRead


class ResultTraceRead(BaseModel):
    # Context of the result, so the reviewer knows exactly what the trace explains (HU-25 AC 1).
    result_id: UUID
    organization_id: UUID
    organization_name: str
    assessment_id: UUID
    assessment_title: str
    control_code: str
    control_title: str
    result_version: int
    result_author: Literal["agent", "aligo_consultant"]

    # The decision that produced this result version. None when the result has no linked decision.
    result_trace_id: UUID | None

    # Every recorded decision for this control in this assessment, oldest first (HU-25 AC 2).
    steps: list[DecisionTraceRead] = Field(default_factory=list)
