"""Record immutable gap analysis runs when an assessment closes or is regenerated.

Revision ID: 20261125_0012
Revises: 20261116_0011
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20261125_0012"
down_revision: Union[str, None] = "20261116_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gap_analysis_runs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_id", sa.Uuid(), nullable=False),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("clock_timestamp()"), nullable=False),
        sa.Column("gap_count", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint("trigger IN ('completion', 'regeneration')", name="ck_gap_analysis_runs_trigger"),
        sa.CheckConstraint("gap_count >= 0", name="ck_gap_analysis_runs_gap_count_non_negative"),
        sa.ForeignKeyConstraint(
            ["organization_id", "assessment_id"],
            ["assessments.organization_id", "assessments.id"],
            name="fk_gap_analysis_runs_assessment_same_org",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["users.id"], ondelete="SET NULL",
            name="fk_gap_analysis_runs_requested_by_user_id_users",
        ),
    )
    op.create_index(
        "ix_gap_analysis_runs_assessment_created", "gap_analysis_runs", ["assessment_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_gap_analysis_runs_assessment_created", table_name="gap_analysis_runs")
    op.drop_table("gap_analysis_runs")
