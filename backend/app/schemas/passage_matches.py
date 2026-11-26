"""Response of the passage matches of an assessment (HU-12)."""

from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.report import LinkedEvidenceVerification


class PassageLocator(BaseModel):
    # Page is known for PDFs uploaded since HU-12 (their pages are kept apart); otherwise null.
    page: int | None = None
    section: str | None = None
    # Offsets of the passage in the file's extracted text, end exclusive.
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)


class PassageMatchRead(BaseModel):
    organization_id: UUID
    assessment_id: UUID
    assessment_control_id: UUID
    control_code: str
    evidence_file_id: UUID
    file_name: str
    # document_span:<file id>[#page=<n>], the reference format of traces and evidence_refs.
    reference: str
    locator: PassageLocator
    excerpt: str = Field(max_length=300)
    matched_terms: list[str]
    confidence: float = Field(ge=0, le=1)
    matcher_version: str
    # A match is a suggestion, never verified evidence: the same marker and label as linked files
    # in the report ("Not yet verified by Aligo").
    verification: LinkedEvidenceVerification = "not_verified"
    # The file is already linked to this control (evidence_control_links). Linking a file does
    # not verify it either.
    linked: bool


class PassageMatchList(BaseModel):
    organization_id: UUID
    assessment_id: UUID
    matcher_version: str
    min_confidence: float
    files_checked: int
    # In-scope controls the matcher has no terms for: they can get no match, which is not the
    # same as "no relevant passage".
    controls_without_terms: list[str]
    matches: list[PassageMatchRead]
