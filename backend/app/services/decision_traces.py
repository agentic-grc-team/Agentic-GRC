"""Store and read reasoning traces (AGRC-15)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DecisionTraceRecord
from app.schemas.decision_trace import DecisionTrace


def record_trace(db: Session, trace: DecisionTrace) -> DecisionTraceRecord:
    """Save one validated decision. Traces are never updated or deleted."""
    record = DecisionTraceRecord(**trace.model_dump(mode="json"))
    db.add(record)
    db.commit()
    db.refresh(record)
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
