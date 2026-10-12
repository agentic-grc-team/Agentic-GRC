"""Store and read reasoning traces (AGRC-15)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DecisionTraceRecord
from app.schemas.decision_trace import DecisionTrace


def record_trace(db: Session, trace: DecisionTrace) -> DecisionTraceRecord:
    """Add one validated decision to the current transaction. Traces are never updated or deleted.

    It only flushes: the caller commits, so a decision and the data it explains
    (for example an expert review) are saved together or not at all.
    """
    record = DecisionTraceRecord(**trace.model_dump())
    db.add(record)
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
