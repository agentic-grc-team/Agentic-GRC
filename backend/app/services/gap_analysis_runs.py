"""Persist a diagnosis on completion and on explicit regeneration (HU-16)."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import GapAnalysisRun
from app.schemas.gaps import GapList
from app.services.gaps import build_gap_list
from app.services.reports.builder import build_report_view
from app.services.reports.source import DbReportSource


def record_gap_analysis_run(
    db: Session,
    organization_id: UUID,
    assessment_id: UUID,
    *,
    trigger: str,
    requested_by_user_id: UUID | None = None,
) -> GapAnalysisRun:
    """Save the gap list in the writer's transaction; never persist a partial run."""
    data = DbReportSource().load(db, organization_id, assessment_id)
    if data is None:
        raise ValueError("Cannot generate gaps for an unknown assessment.")
    generated_at = datetime.now(timezone.utc)
    view = build_report_view(data, generated_at)
    gaps = build_gap_list(data, generated_at, view=view)
    run = GapAnalysisRun(
        organization_id=organization_id,
        assessment_id=assessment_id,
        trigger=trigger,
        requested_by_user_id=requested_by_user_id,
        gap_count=len(gaps.gaps),
        snapshot=gaps.model_dump(mode="json"),
    )
    db.add(run)
    db.flush()
    return run


def list_gap_analysis_runs(db: Session, organization_id: UUID, assessment_id: UUID) -> list[GapAnalysisRun]:
    return list(
        db.scalars(
            select(GapAnalysisRun)
            .where(
                GapAnalysisRun.organization_id == organization_id,
                GapAnalysisRun.assessment_id == assessment_id,
            )
            .order_by(GapAnalysisRun.created_at.desc(), GapAnalysisRun.id.desc())
        )
    )


def run_gap_list(run: GapAnalysisRun) -> GapList:
    return GapList.model_validate(run.snapshot)
