"""Response of the gap list (HU-17): the gaps of an assessment ordered by criticality."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.report import (
    ControlStatus,
    EvidenceReference,
    FinalBasis,
    LinkedEvidenceFile,
    ReportView,
)


class GapRisk(BaseModel):
    name: str
    severity: str


class GapRemediation(BaseModel):
    """HU-18: what to do about the gap and why, from the provisional template of its control."""

    # The issue (consequence of the gap) and the requirement (target state) are a matched pair.
    statement: str
    issue: str
    requirement: str
    task: str
    task_description: str
    # Ordered steps. A partially implemented control gets steps that start from what exists.
    how_to: list[str]
    dependency: str  # People, Process or Technology
    time_horizon: str  # Short term, Mid term or Long term
    # The proof that will show the gap is closed (the KB evidence examples of the control's question).
    evidence_to_close: list[str]
    # Cites the status, the KB question, the recommended task and the HU-17 priority reason.
    justification: str


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
    # HU-16: the evidence behind the result, or an explicit statement that there is none. Files
    # linked after the review are listed (marked added_after_review) but do not count against evidence_absent.
    evidence: list[EvidenceReference] = []
    linked_evidence: list[LinkedEvidenceFile] = []
    evidence_absent: bool
    # HU-18: null when the gap is not classified or its control has no remediation template, so no
    # recommendation is invented. The recommendation never changes the status, priority or risks.
    remediation: GapRemediation | None = None


class GapList(BaseModel):
    organization_id: UUID
    assessment_id: UUID
    generated_at: datetime
    rules_id: str
    rules_version: str
    rules_provisional: bool
    # HU-18: the remediation templates the recommendations come from. Every recommendation is
    # preliminary until a consultant reviews it, and provisional until Aligo confirms the templates.
    remediation_rules_id: str
    remediation_rules_version: str
    remediation_rules_provisional: bool
    gaps: list[Gap]
    # Controls without a final result yet (no result, awaiting review, or rejected or modified and
    # waiting for a new version). They are not gaps until a consultant has confirmed them.
    pending_controls: int


class ReportPreview(ReportView):
    """The report page's data: the report view plus the gap list built from that same view.

    Only the on-screen preview carries the gap list. The PDF and JSON exports keep ReportView.
    """

    gap_list: GapList
