"""Response of the gap list (HU-17): the gaps of an assessment ordered by criticality."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.report import ControlStatus, FinalBasis


class GapRisk(BaseModel):
    name: str
    severity: str


class Gap(BaseModel):
    control_code: str
    control_title: str
    control_status: ControlStatus
    status_label: str
    # False when the control has no classification rule: no priority or risks are invented.
    classified: bool
    priority: str | None = None
    risks: list[GapRisk] = []
    reason: str | None = None
    # The control result the gap is based on: its version and how it became final.
    result_version: int
    basis: FinalBasis
    explanation: str
    evidence_pending: bool = False


class GapList(BaseModel):
    organization_id: UUID
    assessment_id: UUID
    generated_at: datetime
    rules_id: str
    rules_version: str
    rules_provisional: bool
    gaps: list[Gap]
    # Controls without a reviewed result yet. They are not gaps until a consultant has confirmed them.
    pending_controls: int
