"""Add assessments, assessment_controls, control_results and control_result_reviews; link decision_traces to assessments (AGRC-61).

Revision ID: 20261013_0007
Revises: 20261010_0006
Create Date: 2026-10-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '20261013_0007'
down_revision: Union[str, None] = '20261010_0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create tables in order
    op.create_table('assessments',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('framework_code', sa.String(length=50), server_default='NIST-CSF', nullable=False),
        sa.Column('framework_version', sa.String(length=30), server_default='2.0', nullable=False),
        sa.Column('kb_version', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='draft', nullable=False),
        sa.Column('created_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at", name=op.f('ck_assessments_dates_order')),
        sa.CheckConstraint("length(btrim(title)) > 0", name=op.f('ck_assessments_title_not_blank')),
        sa.CheckConstraint("status <> 'completed' OR completed_at IS NOT NULL", name=op.f('ck_assessments_completed_at')),
        sa.CheckConstraint("status IN ('draft', 'in_progress', 'awaiting_review', 'completed')", name=op.f('ck_assessments_status')),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_assessments_created_by_user_id_users'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_assessments_organization_id_organizations')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_assessments')),
        sa.UniqueConstraint('organization_id', 'id', name='uq_assessments_org_id')
    )

    op.create_table('assessment_controls',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('assessment_id', sa.Uuid(), nullable=False),
        sa.Column('control_code', sa.String(length=20), nullable=False),
        sa.Column('control_title', sa.String(length=500), nullable=False),
        sa.Column('in_scope', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('scope_rationale', sa.Text(), nullable=True),
        sa.Column('added_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("control_code ~ '^(GV|ID|PR|DE|RS|RC)\\.[A-Z]{2}-[0-9]{2}$'", name=op.f('ck_assessment_controls_control_code_format')),
        sa.CheckConstraint("in_scope OR (scope_rationale IS NOT NULL AND length(btrim(scope_rationale)) > 0)", name=op.f('ck_assessment_controls_scope_rationale')),
        sa.CheckConstraint("length(btrim(control_title)) > 0", name=op.f('ck_assessment_controls_title_not_blank')),
        sa.ForeignKeyConstraint(['added_by_user_id'], ['users.id'], name=op.f('fk_assessment_controls_added_by_user_id_users'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id', 'assessment_id'], ['assessments.organization_id', 'assessments.id'], name='fk_assessment_controls_assessment_same_org'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_assessment_controls')),
        sa.UniqueConstraint('assessment_id', 'control_code', name='uq_assessment_controls_assessment_code'),
        sa.UniqueConstraint('organization_id', 'assessment_id', 'id', name='uq_assessment_controls_org_assessment_id')
    )

    op.create_table('control_results',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('assessment_id', sa.Uuid(), nullable=False),
        sa.Column('assessment_control_id', sa.Uuid(), nullable=False),
        sa.Column('version_no', sa.Integer(), nullable=False),
        sa.Column('based_on_result_id', sa.Uuid(), nullable=True),
        sa.Column('author_actor', sa.String(length=32), nullable=False),
        sa.Column('author_user_id', sa.Uuid(), nullable=True),
        sa.Column('control_status', sa.String(length=32), nullable=False),
        sa.Column('explanation', sa.Text(), nullable=False),
        sa.Column('justification', sa.Text(), nullable=True),
        sa.Column('not_assessed_reason', sa.Text(), nullable=True),
        sa.Column('maturity_current', sa.SmallInteger(), nullable=True),
        sa.Column('maturity_target', sa.SmallInteger(), nullable=True),
        sa.Column('confidence', sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column('requires_human_review', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('evidence_pending', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('evidence_summary', sa.Text(), nullable=True),
        sa.Column('evidence_refs', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('trace_id', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
        sa.CheckConstraint("(author_actor = 'agent') = (author_user_id IS NULL)", name=op.f('ck_control_results_author_user_matches_actor')),
        sa.CheckConstraint("author_actor IN ('agent', 'aligo_consultant')", name=op.f('ck_control_results_author_actor')),
        sa.CheckConstraint("based_on_result_id IS NULL OR based_on_result_id <> id", name=op.f('ck_control_results_not_based_on_self')),
        sa.CheckConstraint("confidence IS NULL OR confidence BETWEEN 0 AND 1", name=op.f('ck_control_results_confidence_range')),
        sa.CheckConstraint("control_status <> 'not_applicable' OR (justification IS NOT NULL AND length(btrim(justification)) > 0)", name=op.f('ck_control_results_not_applicable_justified')),
        sa.CheckConstraint("control_status <> 'not_assessed' OR (not_assessed_reason IS NOT NULL AND length(btrim(not_assessed_reason)) > 0)", name=op.f('ck_control_results_not_assessed_reason')) ,
        sa.CheckConstraint("control_status IN ('implemented', 'partially_implemented', 'not_implemented', 'not_applicable', 'not_assessed')", name=op.f('ck_control_results_control_status')),
        sa.CheckConstraint("jsonb_typeof(evidence_refs) = 'array'", name=op.f('ck_control_results_evidence_refs_array')),
        sa.CheckConstraint("length(btrim(explanation)) > 0", name=op.f('ck_control_results_explanation_not_blank')),
        sa.CheckConstraint("maturity_current IS NULL OR maturity_current BETWEEN 1 AND 5", name=op.f('ck_control_results_maturity_current_range')),
        sa.CheckConstraint("maturity_target IS NULL OR maturity_target BETWEEN 1 AND 5", name=op.f('ck_control_results_maturity_target_range')),
        sa.CheckConstraint("version_no >= 1", name=op.f('ck_control_results_version_positive')),
        sa.ForeignKeyConstraint(['author_user_id'], ['users.id'], name=op.f('fk_control_results_author_user_id_users')),
        sa.ForeignKeyConstraint(['organization_id', 'assessment_id', 'assessment_control_id'], ['assessment_controls.organization_id', 'assessment_controls.assessment_id', 'assessment_controls.id'], name='fk_control_results_control_same_assessment'),
        sa.ForeignKeyConstraint(['organization_id', 'assessment_id', 'based_on_result_id'], ['control_results.organization_id', 'control_results.assessment_id', 'control_results.id'], name='fk_control_results_based_on_same_assessment'),
        sa.ForeignKeyConstraint(['organization_id', 'assessment_id', 'trace_id'], ['decision_traces.organization_id', 'decision_traces.assessment_id', 'decision_traces.id'], name='fk_control_results_trace_same_assessment'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_control_results')),
        sa.UniqueConstraint('assessment_control_id', 'version_no', name='uq_control_results_control_version'),
        sa.UniqueConstraint('organization_id', 'assessment_id', 'id', name='uq_control_results_org_assessment_id')
    )

    op.create_table('control_result_reviews',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('assessment_id', sa.Uuid(), nullable=False),
        sa.Column('control_result_id', sa.Uuid(), nullable=False),
        sa.Column('outcome', sa.String(length=16), nullable=False),
        sa.Column('resulting_result_id', sa.Uuid(), nullable=True),
        sa.Column('comment', sa.Text(), server_default='', nullable=False),
        sa.Column('reviewed_by_user_id', sa.Uuid(), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('review_trace_id', sa.Uuid(), nullable=True),
        sa.CheckConstraint("(outcome = 'modified') = (resulting_result_id IS NOT NULL)", name=op.f('ck_control_result_reviews_modified_has_result')),
        sa.CheckConstraint("outcome = 'accepted' OR length(btrim(comment)) > 0", name=op.f('ck_control_result_reviews_comment_required')),
        sa.CheckConstraint("outcome IN ('accepted', 'modified', 'rejected')", name=op.f('ck_control_result_reviews_outcome')),
        sa.CheckConstraint("resulting_result_id IS NULL OR resulting_result_id <> control_result_id", name=op.f('ck_control_result_reviews_resulting_differs')),
        sa.ForeignKeyConstraint(['organization_id', 'assessment_id', 'control_result_id'], ['control_results.organization_id', 'control_results.assessment_id', 'control_results.id'], name='fk_control_result_reviews_result_same_assessment'),
        sa.ForeignKeyConstraint(['organization_id', 'assessment_id', 'resulting_result_id'], ['control_results.organization_id', 'control_results.assessment_id', 'control_results.id'], name='fk_control_result_reviews_resulting_same_assessment'),
        sa.ForeignKeyConstraint(['organization_id', 'assessment_id', 'review_trace_id'], ['decision_traces.organization_id', 'decision_traces.assessment_id', 'decision_traces.id'], name='fk_control_result_reviews_trace_same_assessment'),
        sa.ForeignKeyConstraint(['reviewed_by_user_id'], ['users.id'], name=op.f('fk_control_result_reviews_reviewed_by_user_id_users')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_control_result_reviews')),
        sa.UniqueConstraint('control_result_id', name='uq_control_result_reviews_result')
    )

    # 2. Index on assessments
    op.create_index('ix_assessments_org_created', 'assessments', ['organization_id', 'created_at'], unique=False)

    # 3. Append-only protection for audit tables (control_results and control_result_reviews)
    op.execute(sa.text(
        "CREATE FUNCTION public.reject_result_history_change() RETURNS trigger LANGUAGE plpgsql AS $$ "
        "BEGIN RAISE EXCEPTION '% is append-only: % is not allowed', TG_TABLE_NAME, TG_OP; END $$"
    ))
    op.execute(sa.text(
        "CREATE TRIGGER trg_control_results_append_only "
        "BEFORE UPDATE OR DELETE ON public.control_results "
        "FOR EACH ROW EXECUTE FUNCTION public.reject_result_history_change()"
    ))
    op.execute(sa.text(
        "CREATE TRIGGER trg_control_results_no_truncate "
        "BEFORE TRUNCATE ON public.control_results "
        "FOR EACH STATEMENT EXECUTE FUNCTION public.reject_result_history_change()"
    ))
    op.execute(sa.text(
        "CREATE TRIGGER trg_control_result_reviews_append_only "
        "BEFORE UPDATE OR DELETE ON public.control_result_reviews "
        "FOR EACH ROW EXECUTE FUNCTION public.reject_result_history_change()"
    ))
    op.execute(sa.text(
        "CREATE TRIGGER trg_control_result_reviews_no_truncate "
        "BEFORE TRUNCATE ON public.control_result_reviews "
        "FOR EACH STATEMENT EXECUTE FUNCTION public.reject_result_history_change()"
    ))

    # 4. Enable RLS on all four tables
    op.execute(sa.text('ALTER TABLE public."assessments" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text('ALTER TABLE public."assessment_controls" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text('ALTER TABLE public."control_results" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text('ALTER TABLE public."control_result_reviews" ENABLE ROW LEVEL SECURITY'))

    # 5. Composite foreign key from decision_traces to assessments
    # Existing traces would point to assessments that do not exist yet. Stop with a clear message instead of a raw FK error.
    op.execute(sa.text(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM public.decision_traces) THEN "
        "RAISE EXCEPTION 'Migration 0007: decision_traces already has rows. They must be linked to real assessments before applying this migration.'; "
        "END IF; END $$"
    ))
    # Checked on Supabase on 2026-10-12: migration 0006 applied, decision_traces has 0 rows.
    op.create_foreign_key(
        "fk_decision_traces_assessment_same_org",
        "decision_traces",
        "assessments",
        ["organization_id", "assessment_id"],
        ["organization_id", "id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_decision_traces_assessment_same_org", "decision_traces", type_="foreignkey")
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_control_result_reviews_no_truncate ON public.control_result_reviews"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_control_result_reviews_append_only ON public.control_result_reviews"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_control_results_no_truncate ON public.control_results"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_control_results_append_only ON public.control_results"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS public.reject_result_history_change()"))
    op.drop_index("ix_assessments_org_created", table_name="assessments")
    op.drop_table("control_result_reviews")
    op.drop_table("control_results")
    op.drop_table("assessment_controls")
    op.drop_table("assessments")
