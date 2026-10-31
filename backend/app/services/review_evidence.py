"""Read-only evidence context for an authorized expert review (AGRC-74)."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    AssessmentControl,
    AssessmentSession,
    ControlResult,
    DecisionTraceRecord,
    EvidenceFile,
    InterviewTurn,
    User,
)
from app.schemas.evidence import EvidenceFileRead
from app.schemas.expert_review import ReviewEvidence, ReviewEvidenceSource
from app.security.expert_reviews import require_expert_review_access
from app.services.evidence_links import (
    evidence_file_id_from_reference,
    list_evidence_for_control,
)


def _source_entries(entries):
    """Read saved source entries, tolerating malformed or older JSON."""
    if not isinstance(entries, list):
        return [], int(bool(entries))

    sources = []
    skipped = 0

    for entry in entries:
        if not isinstance(entry, dict):
            skipped += 1
            continue

        reference = entry.get("reference", entry.get("ref"))

        if (
            not isinstance(reference, str)
            or not reference.strip()
            or len(reference) > 500
        ):
            skipped += 1
            continue

        kind = entry.get("source_type", entry.get("type"))

        if kind not in ("document_span", "interview_turn"):
            kind = "other"

        excerpt = entry.get("excerpt")

        if isinstance(excerpt, str):
            excerpt = excerpt.strip()[:1000] or None
        else:
            excerpt = None

        sources.append(
            ReviewEvidenceSource(
                source_type=kind,
                reference=reference.strip(),
                excerpt=excerpt,
            )
        )

    return sources, skipped


INTERVIEW_REFERENCE_PREFIX = "interview_turn:"
MAX_TRANSCRIPT_EXCERPT = 1000


def _interview_turn_id(reference: str) -> UUID | None:
    if not reference.startswith(INTERVIEW_REFERENCE_PREFIX):
        return None

    try:
        return UUID(reference[len(INTERVIEW_REFERENCE_PREFIX):])
    except ValueError:
        return None


def _resolve_interview_statements(
    db: Session,
    result: ControlResult,
    sources: list[ReviewEvidenceSource],
) -> None:
    """Quote cited participant answers from this assessment's transcript.

    A cited turn that is found replaces any saved excerpt, so a result cannot
    show text the participant never gave. Other citations keep their saved
    excerpt and stay marked as not quoted from the transcript.
    """
    turn_ids = {
        turn_id
        for source in sources
        if source.source_type == "interview_turn"
        and (turn_id := _interview_turn_id(source.reference)) is not None
    }

    if not turn_ids:
        return

    rows = db.execute(
        select(InterviewTurn.id, InterviewTurn.content)
        .join(
            AssessmentSession,
            (AssessmentSession.organization_id == InterviewTurn.organization_id)
            & (AssessmentSession.id == InterviewTurn.session_id),
        )
        .where(
            InterviewTurn.id.in_(turn_ids),
            InterviewTurn.organization_id == result.organization_id,
            InterviewTurn.speaker == "participant",
            AssessmentSession.assessment_id == result.assessment_id,
        )
    ).all()

    statements = {turn_id: content for turn_id, content in rows}

    for source in sources:
        if source.source_type != "interview_turn":
            continue

        content = statements.get(_interview_turn_id(source.reference))

        if content is None:
            continue

        content = content.strip()

        if len(content) > MAX_TRANSCRIPT_EXCERPT:
            content = content[: MAX_TRANSCRIPT_EXCERPT - 3] + "..."

        source.excerpt = content or None
        source.from_transcript = True


def get_review_evidence(
    db: Session,
    result_id: UUID,
    user: User,
) -> ReviewEvidence:
    result = db.get(ControlResult, result_id)

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Review result not found.",
        )

    require_expert_review_access(db, result.organization_id, user)

    control = db.scalar(
        select(AssessmentControl).where(
            AssessmentControl.id == result.assessment_control_id,
            AssessmentControl.organization_id == result.organization_id,
            AssessmentControl.assessment_id == result.assessment_id,
        )
    )

    if control is None:
        raise HTTPException(
            status_code=404,
            detail="Assessment control not found.",
        )

    sources, skipped = _source_entries(result.evidence_refs)

    trace = None

    if result.trace_id:
        trace = db.get(DecisionTraceRecord, result.trace_id)

    # Only use the matching agent status trace for this control.
    if (
        trace is not None
        and trace.organization_id == result.organization_id
        and trace.assessment_id == result.assessment_id
        and trace.actor_type == "agent"
        and trace.decision_type == "status_assessed"
        and control.control_code in trace.control_ids
    ):
        trace_sources, trace_skipped = _source_entries(trace.sources)
        sources.extend(trace_sources)
        skipped += trace_skipped

    # The same citation can occur in both the result and its trace.
    unique = {}

    for source in sources:
        key = (source.source_type, source.reference)

        if key not in unique:
            unique[key] = source
        elif not unique[key].excerpt:
            unique[key].excerpt = source.excerpt

    sources = list(unique.values())

    document_ids = set()

    for source in sources:
        if source.source_type == "document_span":
            document_id = evidence_file_id_from_reference(
                source.reference
            )

            if document_id is not None:
                document_ids.add(document_id)

    documents = {}

    if document_ids:
        rows = db.scalars(
            select(EvidenceFile).where(
                EvidenceFile.id.in_(document_ids),
                EvidenceFile.organization_id == result.organization_id,
                or_(
                    EvidenceFile.assessment_id.is_(None),
                    EvidenceFile.assessment_id == result.assessment_id,
                ),
            )
        )

        for row in rows:
            documents[row.id] = EvidenceFileRead.model_validate(row)

    for source in sources:
        if source.source_type == "document_span":
            document_id = evidence_file_id_from_reference(
                source.reference
            )
            source.document = documents.get(document_id)

            if source.document is None:
                # Do not expose claimed excerpts from unresolved documents.
                source.excerpt = None

    _resolve_interview_statements(db, result, sources)

    linked = list_evidence_for_control(
        db,
        result.organization_id,
        control.id,
        result.assessment_id,
    )

    linked_documents = []

    for row in linked:
        if (
            row.assessment_id is None
            or row.assessment_id == result.assessment_id
        ):
            linked_documents.append(
                EvidenceFileRead.model_validate(row)
            )

    return ReviewEvidence(
        result_id=str(result.id),
        evidence_pending=result.evidence_pending,
        sources=sources,
        linked_documents=linked_documents,
        skipped_source_count=skipped,
    )
