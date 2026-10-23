"""Store and read assessments (AGRC-61, AGRC-73)."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import Assessment, AssessmentControl
from app.schemas.assessments import DEFAULT_KB_VERSION, AssessmentCreate
from app.services.assessment_scope import controls_for_kb_version


def start_assessment(
    db: Session,
    organization_id: UUID,
    created_by_user_id: UUID | None,
    data: AssessmentCreate,
) -> Assessment:
    """Start an assessment for an organization, with the controls of its knowledge-base version in scope.

    Starting an assessment is a complete action, so this service commits (unlike record_trace).
    The assessment and its controls are committed together: if a control cannot be added,
    nothing is saved, so there is never an assessment without controls.
    """
    kb_version = data.kb_version or DEFAULT_KB_VERSION
    assessment = Assessment(
        organization_id=organization_id,
        created_by_user_id=created_by_user_id,
        title=data.title,
        framework_code="NIST-CSF",
        framework_version="2.0",
        kb_version=kb_version,
        status="in_progress",
        started_at=datetime.now(timezone.utc),
    )
    try:
        db.add(assessment)
        db.flush()  # the controls need the assessment id
        db.add_all(
            AssessmentControl(
                organization_id=organization_id,
                assessment_id=assessment.id,
                control_code=code,
                control_title=title,
                in_scope=True,
                added_by_user_id=created_by_user_id,
            )
            for code, title in controls_for_kb_version(kb_version)
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(assessment)
    return assessment


def list_assessments(db: Session, organization_id: UUID) -> list[Assessment]:
    """All assessments of one organization, newest first. Always filtered by organization."""
    statement = (
        select(Assessment)
        .where(Assessment.organization_id == organization_id)
        .order_by(Assessment.created_at.desc(), Assessment.id)
    )
    return list(db.scalars(statement))


def get_assessment(db: Session, organization_id: UUID, assessment_id: UUID) -> Assessment | None:
    """Read one assessment, filtered by both organization and assessment ID."""
    statement = (
        select(Assessment)
        .where(
            Assessment.organization_id == organization_id,
            Assessment.id == assessment_id,
        )
    )
    return db.scalars(statement).first()
