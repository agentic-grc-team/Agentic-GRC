"""Store and read evidence file metadata."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EvidenceFile


def store_evidence_file(
    db: Session,
    organization_id: UUID,
    uploaded_by_user_id: UUID | None,
    assessment_id: UUID | None,
    original_filename: str,
    stored_filename: str,
    content_type: str | None,
    file_extension: str,
    size_bytes: int,
    sha256: str,
    extracted_text: str,
) -> EvidenceFile:
    """Record one uploaded evidence document. A complete action, so this service commits."""
    record = EvidenceFile(
        organization_id=organization_id,
        assessment_id=assessment_id,
        uploaded_by_user_id=uploaded_by_user_id,
        original_filename=original_filename,
        stored_filename=stored_filename,
        content_type=content_type,
        file_extension=file_extension,
        size_bytes=size_bytes,
        sha256=sha256,
        extracted_text=extracted_text,
    )
    db.add(record)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(record)
    return record


def list_evidence_files(
    db: Session,
    organization_id: UUID,
    assessment_id: UUID | None = None,
) -> list[EvidenceFile]:
    """Evidence of one organization, newest first. Always filtered by organization."""
    statement = select(EvidenceFile).where(EvidenceFile.organization_id == organization_id)
    if assessment_id is not None:
        statement = statement.where(EvidenceFile.assessment_id == assessment_id)
    statement = statement.order_by(EvidenceFile.created_at.desc(), EvidenceFile.id)
    return list(db.scalars(statement))
