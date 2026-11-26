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

ASSESSMENT_STATUS_LABELS: dict[str, str] = {
    "draft": "Draft",
    "in_progress": "In progress",
    "awaiting_review": "Awaiting review",
    "completed": "Completed",
}

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
    "modified_awaiting_consultant_version": "Modified by reviewer — consultant version pending",
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


LinkedEvidenceVerification = Literal["not_verified"]

LINKED_EVIDENCE_VERIFICATION_LABELS: dict[str, str] = {
    "not_verified": "Not yet verified by Aligo",
}


class LinkedEvidenceFile(BaseModel):
    """A file the organization uploaded and linked to a control (evidence_control_links).

    Only metadata goes to the report: never the extracted text. Linked files are not verified yet,
    so they support a result without changing its evidence_pending flag.
    """

    id: UUID  # the evidence file's id: stable even when the same file is uploaded twice
    file_name: str
    file_type: str  # extension in upper case, e.g. "PDF"
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    uploaded_at: datetime
    linked_at: datetime  # when the file was linked to the control
    # True when the file was linked after the result was reviewed, so the reviewer did not see it.
    added_after_review: bool = False
    verification: LinkedEvidenceVerification = "not_verified"
    verification_label: str = LINKED_EVIDENCE_VERIFICATION_LABELS["not_verified"]


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
    linked_evidence: list[LinkedEvidenceFile] = []  # files linked to the control, oldest first

    @model_validator(mode="after")
    def validate_unique_versions(self) -> "ControlInScope":
        version_nos = [v.version_no for v in self.versions]
        if len(version_nos) != len(set(version_nos)):
            raise ValueError(f"Control {self.code} has duplicate version_no values.")
        return self


class ReportInput(BaseModel):
    organization: OrganizationInfo
    assessment: AssessmentInfo
    controls: list[ControlInScope]
    is_demo_data: bool = False


FinalBasis = Literal["accepted_agent_result", "consultant_version"]
PendingReason = Literal[
    "awaiting_review",
    "rejected_awaiting_new_version",
    "modified_awaiting_consultant_version",
    "no_result",
]


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
    linked_evidence: list[LinkedEvidenceFile] = []
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


COMPLIANCE_PARTIAL_WEIGHT = 0.5
COMPLIANCE_DEFINITION = (
    "Compliance = (Implemented + 0.5 × Partially implemented) / "
    "(Implemented + Partially implemented + Not implemented), over final reviewed results only. "
    "Not applicable exclusions, Not assessed results and controls pending review are left out of "
    "both numerator and denominator and are reported next to the figure."
)


class ComplianceSummary(BaseModel):
    """One compliance figure for the assessment (HU-23), with everything needed to explain it.

    Only final reviewed results count. When no final result is Implemented, Partially implemented or
    Not implemented, the figure is unavailable (value_pct None), never 0% or 100%.
    """

    available: bool
    value_pct: float | None = None  # numerator / denominator * 100, rounded to 1 decimal
    numerator: float = 0.0  # implemented + 0.5 * partially_implemented
    denominator: int = 0  # implemented + partially_implemented + not_implemented
    implemented: int = 0
    partially_implemented: int = 0
    not_implemented: int = 0
    excluded_not_applicable: int = 0  # final exclusions, outside the figure
    not_assessed: int = 0  # final results marked not assessed, outside the figure
    pending: int = 0  # controls without a final result yet, outside the figure
    definition: str = COMPLIANCE_DEFINITION


class ReportSummary(BaseModel):
    controls_in_scope: int
    finalized: int  # final results + exclusions
    pending: int
    final_with_evidence_pending: int = 0
    coverage_pct: float  # finalized / controls_in_scope * 100, rounded to 1 decimal; 0.0 if no controls
    status_counts: dict[str, int]  # keys: implemented, partially_implemented, not_implemented, not_assessed (always all 4, zero if none). Excludes not_applicable.
    compliance: ComplianceSummary | None = None  # HU-23; always set by the builder


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


REPORT_EXPORT_FORMAT = "agentic-grc.assessment-report"
REPORT_EXPORT_VERSION = "1.2"  # 1.1 adds results[].linked_evidence; 1.2 adds summary.compliance and comparison


ComparisonChange = Literal["improved", "declined", "unchanged", "not_comparable"]
ComparisonWarningCode = Literal[
    "current_not_completed",
    "framework_differs",
    "kb_version_differs",
    "scope_differs",
    "compliance_unavailable",
]


class ComparedAssessment(BaseModel):
    id: UUID
    title: str
    status: AssessmentStatus
    completed_at: datetime | None = None
    framework: str
    kb_version: str
    compliance: ComplianceSummary


class ComparisonWarning(BaseModel):
    code: ComparisonWarningCode
    message: str


class ComparisonScope(BaseModel):
    added: list[str] = []  # control codes only in the current assessment
    removed: list[str] = []  # control codes only in the previous assessment
    common: int = 0


class ControlComparison(BaseModel):
    code: str
    title: str
    # Final status, or "pending" when the control has no final result in that assessment.
    previous_status: str
    current_status: str
    change: ComparisonChange


class AssessmentComparison(BaseModel):
    """Current assessment against an earlier completed one of the same organization (HU-24)."""

    current: ComparedAssessment
    previous: ComparedAssessment
    # Percentage points, current minus previous, rounded to 1 decimal. None when either is unavailable.
    compliance_change_pct: float | None = None
    warnings: list[ComparisonWarning] = []
    scope: ComparisonScope
    changed_controls: int = 0  # controls in both assessments whose status changed
    controls: list[ControlComparison] = []  # controls in both assessments, sorted by code


class ComparisonCandidate(BaseModel):
    id: UUID
    title: str
    completed_at: datetime
    framework: str
    kb_version: str


class ReportExport(BaseModel):
    """Structured export of a report view (HU-21). Same content as the preview and the PDF."""

    export_format: Literal["agentic-grc.assessment-report"] = REPORT_EXPORT_FORMAT
    export_version: Literal["1.2"] = REPORT_EXPORT_VERSION
    report: ReportView
    comparison: AssessmentComparison | None = None  # only when ?compare_with= is given
