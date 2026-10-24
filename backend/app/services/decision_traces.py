"""Store and read reasoning traces (AGRC-15)."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AssessmentSession,
    DecisionTraceRecord,
    DecisionTraceSourceRecord,
    InterviewTurn,
)
from app.schemas.decision_trace import DecisionTrace, TraceSource


def record_trace(
    db: Session, trace: DecisionTrace, record_id: UUID | None = None
) -> DecisionTraceRecord:
    """Add one validated decision to the current transaction. Traces are never updated or deleted.

    It only flushes: the caller commits, so a decision and the data it explains
    (for example an expert review) are saved together or not at all.
    """
    record_fields = trace.model_dump()
    if record_id is not None:
        record_fields["id"] = record_id
    record = DecisionTraceRecord(**record_fields)
    db.add(record)
    db.flush()
    return record


def record_interview_trace(
    db: Session,
    trace: DecisionTrace,
    source_turn_ids: Sequence[UUID],
    record_id: UUID | None = None,
) -> DecisionTraceRecord:
    """Persist an agent decision with durable interview-turn references.

    The trace and its source references are written in the caller's transaction.
    The UUID references use the stable interview_turn:<uuid> form; turn text is
    not copied into the trace excerpt by default.
    """
    turn_ids = list(dict.fromkeys(source_turn_ids))
    if not turn_ids:
        raise ValueError("An interview trace must reference at least one persisted turn.")

    matching_turn_ids = set(
        db.scalars(
            select(InterviewTurn.id)
            .join(
                AssessmentSession,
                (InterviewTurn.session_id == AssessmentSession.id)
                & (InterviewTurn.organization_id == AssessmentSession.organization_id),
            )
            .where(
                InterviewTurn.id.in_(turn_ids),
                InterviewTurn.organization_id == trace.organization_id,
                AssessmentSession.assessment_id == trace.assessment_id,
            )
        )
    )
    if matching_turn_ids != set(turn_ids):
        raise ValueError("Every source turn must belong to the trace organization and assessment.")

    sources = [source.model_dump() for source in trace.sources if source.type != "interview_turn"]
    sources.extend(
        TraceSource(type="interview_turn", ref=f"interview_turn:{turn_id}").model_dump()
        for turn_id in turn_ids
    )
    payload = trace.model_dump()
    payload["sources"] = sources
    persisted_trace = DecisionTrace.model_validate(payload)
    existing = db.get(DecisionTraceRecord, record_id) if record_id is not None else None
    if existing is not None:
        if (
            existing.organization_id != trace.organization_id
            or existing.assessment_id != trace.assessment_id
            or existing.decision_type != trace.decision_type
            or existing.output != trace.output
            or existing.prompt_id != trace.prompt_id
        ):
            raise ValueError("The interview trace id was already used for different trace data.")
        return existing

    record = record_trace(db, persisted_trace, record_id=record_id)
    db.add_all(
        DecisionTraceSourceRecord(
            organization_id=trace.organization_id,
            trace_id=record.id,
            source_type="interview_turn",
            interview_turn_id=turn_id,
        )
        for turn_id in turn_ids
    )
    db.flush()
    return record


def list_traces(db: Session, organization_id: UUID, assessment_id: UUID) -> list[DecisionTraceRecord]:
    """All decisions of one assessment, oldest first. Always filtered by organization."""
    statement = (
        select(DecisionTraceRecord)
        .where(
            DecisionTraceRecord.organization_id == organization_id,
            DecisionTraceRecord.assessment_id == assessment_id,
        )
        .order_by(DecisionTraceRecord.created_at, DecisionTraceRecord.id)
    )
    return list(db.scalars(statement))
