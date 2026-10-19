"""Link evidence files to the controls of an assessment, and refer to them from control results."""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import AssessmentControl, EvidenceControlLink, EvidenceFile

DOCUMENT_REFERENCE_PREFIX = "document_span:"


class EvidenceLinkError(Exception):
    """Base class for evidence linking failures."""


class EvidenceNotFoundError(EvidenceLinkError):
    pass


class ControlNotFoundError(EvidenceLinkError):
    pass


class EvidenceAssessmentMismatchError(EvidenceLinkError):
    pass


def document_reference(evidence_file_id: UUID, page: int | None = None) -> str:
    """Reference to an evidence file for a source of a trace or an evidence_refs item.

    Format from docs/design/trace-schema.md: document_span:<document_id>#page=<n>.
    """
    reference = f"{DOCUMENT_REFERENCE_PREFIX}{evidence_file_id}"
    if page is not None:
        reference += f"#page={page}"
    return reference


def evidence_file_id_from_reference(reference: str) -> UUID | None:
    """The evidence file a document reference points to, or None if it is not one."""
    if not reference.startswith(DOCUMENT_REFERENCE_PREFIX):
        return None
    identifier = reference[len(DOCUMENT_REFERENCE_PREFIX):].split("#", 1)[0]
    try:
        return UUID(identifier)
    except ValueError:
        return None


def _find_link(
    db: Session, organization_id: UUID, evidence_file_id: UUID, assessment_control_id: UUID
) -> EvidenceControlLink | None:
    statement = select(EvidenceControlLink).where(
        EvidenceControlLink.organization_id == organization_id,
        EvidenceControlLink.evidence_file_id == evidence_file_id,
        EvidenceControlLink.assessment_control_id == assessment_control_id,
    )
    return db.scalars(statement).first()


def link_evidence_to_control(
    db: Session,
    organization_id: UUID,
    evidence_file_id: UUID,
    assessment_control_id: UUID,
    linked_by_user_id: UUID | None,
) -> tuple[EvidenceControlLink, bool]:
    """Link an evidence file to a control of the same organization.

    Returns the link and whether it was created, so linking the same pair twice is harmless.
    A file that was uploaded for one assessment cannot be linked to a control of another;
    a file uploaded without an assessment can be linked to any control of the organization.
    A complete action, so this service commits.
    """
    evidence = db.scalars(
        select(EvidenceFile).where(
            EvidenceFile.organization_id == organization_id,
            EvidenceFile.id == evidence_file_id,
        )
    ).first()
    if evidence is None:
        raise EvidenceNotFoundError("Evidence file not found.")

    control = db.scalars(
        select(AssessmentControl).where(
            AssessmentControl.organization_id == organization_id,
            AssessmentControl.id == assessment_control_id,
        )
    ).first()
    if control is None:
        raise ControlNotFoundError("Control not found.")

    if evidence.assessment_id is not None and evidence.assessment_id != control.assessment_id:
        raise EvidenceAssessmentMismatchError("Evidence file belongs to a different assessment.")

    existing = _find_link(db, organization_id, evidence_file_id, assessment_control_id)
    if existing is not None:
        return existing, False

    link = EvidenceControlLink(
        organization_id=organization_id,
        assessment_id=control.assessment_id,
        assessment_control_id=control.id,
        evidence_file_id=evidence.id,
        linked_by_user_id=linked_by_user_id,
    )
    db.add(link)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _find_link(db, organization_id, evidence_file_id, assessment_control_id)
        if existing is None:
            raise
        return existing, False
    db.refresh(link)
    return link, True


def unlink_evidence_from_control(
    db: Session,
    organization_id: UUID,
    evidence_file_id: UUID,
    assessment_control_id: UUID,
) -> bool:
    """Remove a link of this organization. Returns False when there was none."""
    result = db.execute(
        delete(EvidenceControlLink).where(
            EvidenceControlLink.organization_id == organization_id,
            EvidenceControlLink.evidence_file_id == evidence_file_id,
            EvidenceControlLink.assessment_control_id == assessment_control_id,
        )
    )
    db.commit()
    return result.rowcount > 0


def list_evidence_for_control(
    db: Session, organization_id: UUID, assessment_control_id: UUID
) -> list[EvidenceFile]:
    """Evidence files linked to one control, newest link first. Always filtered by organization."""
    statement = (
        select(EvidenceFile)
        .join(
            EvidenceControlLink,
            (EvidenceControlLink.organization_id == EvidenceFile.organization_id)
            & (EvidenceControlLink.evidence_file_id == EvidenceFile.id),
        )
        .where(
            EvidenceControlLink.organization_id == organization_id,
            EvidenceControlLink.assessment_control_id == assessment_control_id,
        )
        .order_by(EvidenceControlLink.created_at.desc(), EvidenceFile.id)
    )
    return list(db.scalars(statement))
