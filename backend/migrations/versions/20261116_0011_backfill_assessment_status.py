"""Backfill assessment status from existing results (data only, no schema change).

Until this release nothing moved an assessment past in_progress, so assessments whose results were
already reviewed still show In progress with completed_at null. This applies the rule of
app/services/assessment_status.py once to the existing data:

* in_progress: at least one in-scope control has no result yet;
* awaiting_review: every in-scope control has a result, at least one is not final;
* completed: every in-scope control has a final result (an accepted agent result or a consultant
  version). completed_at is set to the time of this migration, since the real completion time was
  never recorded.

Draft assessments and assessments without in-scope controls are left as they are. From now on the
application keeps the status current (refresh_assessment_status).

Revision ID: 20261116_0011
Revises: 20261020_0010
Create Date: 2026-11-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261116_0011"
down_revision: Union[str, None] = "20261020_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


BACKFILL = sa.text(
    """
    WITH latest AS (
        SELECT DISTINCT ON (assessment_control_id) id, assessment_control_id, author_actor
        FROM public.control_results
        ORDER BY assessment_control_id, version_no DESC
    ),
    counts AS (
        SELECT
            ac.assessment_id,
            count(*) AS in_scope,
            count(latest.id) AS with_result,
            count(*) FILTER (
                WHERE latest.author_actor = 'aligo_consultant'
                   OR (latest.author_actor = 'agent' AND review.outcome = 'accepted')
            ) AS final
        FROM public.assessment_controls AS ac
        LEFT JOIN latest ON latest.assessment_control_id = ac.id
        LEFT JOIN public.control_result_reviews AS review ON review.control_result_id = latest.id
        WHERE ac.in_scope
        GROUP BY ac.assessment_id
    ),
    derived AS (
        SELECT
            assessment_id,
            CASE
                WHEN with_result < in_scope THEN 'in_progress'
                WHEN final < in_scope THEN 'awaiting_review'
                ELSE 'completed'
            END AS status
        FROM counts
    )
    UPDATE public.assessments AS a
    SET status = derived.status,
        completed_at = CASE
            WHEN derived.status = 'completed' THEN coalesce(a.completed_at, now())
            ELSE NULL
        END
    FROM derived
    WHERE a.id = derived.assessment_id
      AND a.status <> 'draft'
      AND (a.status <> derived.status OR (derived.status = 'completed') <> (a.completed_at IS NOT NULL))
    """
)


def upgrade() -> None:
    op.execute(BACKFILL)


def downgrade() -> None:
    # Data only: the previous statuses were wrong, so there is nothing to restore.
    pass
