"""Add the interview persistence slice and private LangGraph schema.

Revision ID: 20261020_0010
Revises: 20261019_0009
Create Date: 2026-10-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20261020_0010"
down_revision: Union[str, None] = "20261019_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ACTOR_TYPE_VALUES = ("agent", "assessed_org_representative", "aligo_consultant")
SESSION_TYPE_VALUES = ("kickoff", "block", "recovery", "evidence_review")
TURN_SPEAKER_VALUES = ("agent", "participant")
TURN_TYPE_VALUES = (
    "question",
    "answer",
    "follow_up",
    "clarification",
    "evidence_request",
    "contradiction_prompt",
    "summary",
)
KB_VERSION_STATUS_VALUES = ("draft", "published", "retired")
SOURCE_TYPE_VALUES = (
    "interview_turn",
    "document_span",
    "tenant_configuration",
    "prior_phase_evidence",
)


def upgrade() -> None:
    bind = op.get_bind()
    # These types are created explicitly below. Disable SQLAlchemy's implicit
    # CREATE TYPE hook when their first table is created, otherwise PostgreSQL
    # sees a duplicate type inside this same migration transaction.
    actor_type = postgresql.ENUM(*ACTOR_TYPE_VALUES, name="actor_type", create_type=False)
    session_type = postgresql.ENUM(*SESSION_TYPE_VALUES, name="session_type", create_type=False)
    turn_speaker = postgresql.ENUM(*TURN_SPEAKER_VALUES, name="turn_speaker", create_type=False)
    turn_type = postgresql.ENUM(*TURN_TYPE_VALUES, name="turn_type", create_type=False)
    kb_version_status = postgresql.ENUM(
        *KB_VERSION_STATUS_VALUES, name="kb_version_status", create_type=False
    )
    source_type = postgresql.ENUM(*SOURCE_TYPE_VALUES, name="source_type", create_type=False)
    for enum_type in (actor_type, session_type, turn_speaker, turn_type, kb_version_status, source_type):
        enum_type.create(bind, checkfirst=True)

    # The checkpointer is infrastructure state and must not be exposed through public/PostgREST.
    op.execute(sa.text("CREATE SCHEMA IF NOT EXISTS agentic_grc_private"))
    op.execute(sa.text("REVOKE ALL ON SCHEMA agentic_grc_private FROM PUBLIC"))
    op.execute(
        sa.text(
            "COMMENT ON SCHEMA agentic_grc_private IS "
            "'Private LangGraph checkpoint state; provisioned by the backend checkpointer.'"
        )
    )

    op.create_table(
        "frameworks",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_frameworks")),
        sa.UniqueConstraint("code", name=op.f("uq_frameworks_code")),
    )
    op.create_table(
        "framework_versions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("framework_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.String(length=30), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["framework_id"], ["frameworks.id"], name=op.f("fk_framework_versions_framework_id_frameworks")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_framework_versions")),
        sa.UniqueConstraint("framework_id", "version", name="uq_framework_versions_framework_version"),
    )
    op.create_table(
        "kb_versions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("framework_version_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=50), nullable=False),
        sa.Column("status", kb_version_status, server_default="draft", nullable=False),
        sa.Column("is_provisional", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("decision_record_ref", sa.String(length=255), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status = 'draft' OR published_at IS NOT NULL", name=op.f("ck_kb_versions_published_at")),
        sa.ForeignKeyConstraint(["framework_version_id"], ["framework_versions.id"], name=op.f("fk_kb_versions_framework_version_id_framework_versions")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kb_versions")),
        sa.UniqueConstraint("label", name=op.f("uq_kb_versions_label")),
    )
    op.create_table(
        "interview_blocks",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("kb_version_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=5), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("audience", sa.Text(), nullable=False),
        sa.Column("estimated_minutes", sa.SmallInteger(), nullable=True),
        sa.Column("sort_order", sa.SmallInteger(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["kb_version_id"], ["kb_versions.id"], name=op.f("fk_interview_blocks_kb_version_id_kb_versions")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interview_blocks")),
        sa.UniqueConstraint("kb_version_id", "code", name="uq_interview_blocks_kb_version_code"),
    )
    op.create_table(
        "assessment_modules",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("kb_version_id", sa.Uuid(), nullable=False),
        sa.Column("block_id", sa.Uuid(), nullable=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["block_id"], ["interview_blocks.id"], name=op.f("fk_assessment_modules_block_id_interview_blocks")),
        sa.ForeignKeyConstraint(["kb_version_id"], ["kb_versions.id"], name=op.f("fk_assessment_modules_kb_version_id_kb_versions")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessment_modules")),
        sa.UniqueConstraint("kb_version_id", "code", name="uq_assessment_modules_kb_version_code"),
    )
    op.create_index("ix_assessment_modules_block_id", "assessment_modules", ["block_id"], unique=False)
    op.create_table(
        "questions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("module_id", sa.Uuid(), nullable=False),
        sa.Column("statement_id", sa.Uuid(), nullable=True),
        sa.Column("remediation_template_id", sa.Uuid(), nullable=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("language_code", sa.String(length=10), server_default="en", nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["module_id"], ["assessment_modules.id"], name=op.f("fk_questions_module_id_assessment_modules")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_questions")),
        sa.UniqueConstraint("module_id", "code", name="uq_questions_module_code"),
    )

    op.create_table(
        "assessment_participants",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("participant_type", actor_type, nullable=False),
        sa.Column("role_title", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("participant_type <> 'agent'", name=op.f("ck_assessment_participants_human")),
        sa.ForeignKeyConstraint(["organization_id", "assessment_id"], ["assessments.organization_id", "assessments.id"], name="fk_assessment_participants_assessment_same_org"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_assessment_participants_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessment_participants")),
        sa.UniqueConstraint("organization_id", "id", name="uq_assessment_participants_tenant"),
    )
    op.create_index("ix_assessment_participants_assessment_id", "assessment_participants", ["assessment_id"], unique=False)
    op.create_table(
        "assessment_sessions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_id", sa.Uuid(), nullable=False),
        sa.Column("session_type", session_type, nullable=False),
        sa.Column("block_id", sa.Uuid(), nullable=True),
        sa.Column("facilitator_user_id", sa.Uuid(), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resume_summary", sa.Text(), nullable=True),
        sa.CheckConstraint("(session_type = 'block') = (block_id IS NOT NULL)", name=op.f("ck_assessment_sessions_block")),
        sa.CheckConstraint("ended_at IS NULL OR started_at IS NULL OR ended_at >= started_at", name=op.f("ck_assessment_sessions_dates")),
        sa.ForeignKeyConstraint(["block_id"], ["interview_blocks.id"], name=op.f("fk_assessment_sessions_block_id_interview_blocks")),
        sa.ForeignKeyConstraint(["facilitator_user_id"], ["users.id"], name=op.f("fk_assessment_sessions_facilitator_user_id_users")),
        sa.ForeignKeyConstraint(["organization_id", "assessment_id"], ["assessments.organization_id", "assessments.id"], name="fk_assessment_sessions_assessment_same_org"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessment_sessions")),
        sa.UniqueConstraint("organization_id", "id", name="uq_assessment_sessions_tenant"),
    )
    op.create_index("ix_assessment_sessions_assessment_id", "assessment_sessions", ["assessment_id"], unique=False)
    op.create_table(
        "session_participants",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("participant_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id", "participant_id"], ["assessment_participants.organization_id", "assessment_participants.id"], name="fk_session_participants_participant_same_org"),
        sa.ForeignKeyConstraint(["organization_id", "session_id"], ["assessment_sessions.organization_id", "assessment_sessions.id"], name="fk_session_participants_session_same_org", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id", "participant_id", name=op.f("pk_session_participants")),
    )
    op.create_table(
        "interview_turns",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("speaker", turn_speaker, nullable=False),
        sa.Column("participant_id", sa.Uuid(), nullable=True),
        sa.Column("turn_type", turn_type, nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=True),
        sa.Column("replies_to_turn_id", sa.Uuid(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("language_code", sa.String(length=10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("(speaker = 'participant') = (participant_id IS NOT NULL)", name=op.f("ck_interview_turns_participant")),
        sa.ForeignKeyConstraint(["organization_id", "participant_id"], ["assessment_participants.organization_id", "assessment_participants.id"], name="fk_interview_turns_participant_same_org"),
        sa.ForeignKeyConstraint(["organization_id", "replies_to_turn_id"], ["interview_turns.organization_id", "interview_turns.id"], name="fk_interview_turns_reply_same_org"),
        sa.ForeignKeyConstraint(["organization_id", "session_id"], ["assessment_sessions.organization_id", "assessment_sessions.id"], name="fk_interview_turns_session_same_org"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], name=op.f("fk_interview_turns_question_id_questions")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interview_turns")),
        sa.UniqueConstraint("organization_id", "id", name="uq_interview_turns_tenant"),
        sa.UniqueConstraint("session_id", "sequence_no", name="uq_interview_turns_session_sequence"),
    )
    op.create_index("ix_interview_turns_session_created", "interview_turns", ["session_id", "created_at"], unique=False)

    # The primary key already makes (organization_id, id) unique in practice;
    # this constraint allows tenant-scoped foreign keys from normalized trace sources.
    op.create_unique_constraint(
        "uq_decision_traces_org_id", "decision_traces", ["organization_id", "id"]
    )
    op.create_table(
        "decision_trace_sources",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("trace_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", source_type, nullable=False),
        sa.Column("interview_turn_id", sa.Uuid(), nullable=True),
        sa.Column("document_chunk_id", sa.Uuid(), nullable=True),
        sa.Column("configuration_item_id", sa.Uuid(), nullable=True),
        sa.Column("prior_phase_finding_id", sa.Uuid(), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "num_nonnulls(interview_turn_id, document_chunk_id, configuration_item_id, prior_phase_finding_id) = 1",
            name=op.f("ck_decision_trace_sources_one_reference"),
        ),
        sa.CheckConstraint(
            "(source_type = 'interview_turn') = (interview_turn_id IS NOT NULL)",
            name=op.f("ck_decision_trace_sources_type_turn"),
        ),
        sa.CheckConstraint(
            "(source_type = 'document_span') = (document_chunk_id IS NOT NULL)",
            name=op.f("ck_decision_trace_sources_type_document"),
        ),
        sa.CheckConstraint(
            "(source_type = 'tenant_configuration') = (configuration_item_id IS NOT NULL)",
            name=op.f("ck_decision_trace_sources_type_configuration"),
        ),
        sa.CheckConstraint(
            "(source_type = 'prior_phase_evidence') = (prior_phase_finding_id IS NOT NULL)",
            name=op.f("ck_decision_trace_sources_type_prior_phase"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "interview_turn_id"],
            ["interview_turns.organization_id", "interview_turns.id"],
            name="fk_decision_trace_sources_turn_same_org",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "trace_id"],
            ["decision_traces.organization_id", "decision_traces.id"],
            name="fk_decision_trace_sources_trace_same_org",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_decision_trace_sources")),
        sa.UniqueConstraint("trace_id", "interview_turn_id", name="uq_trace_source_turn"),
    )
    op.create_index("ix_decision_trace_sources_trace_id", "decision_trace_sources", ["trace_id"], unique=False)
    op.execute(sa.text(
        "CREATE FUNCTION public.reject_decision_trace_source_change() RETURNS trigger "
        "LANGUAGE plpgsql AS $$ BEGIN "
        "RAISE EXCEPTION 'decision_trace_sources is append-only: % is not allowed', TG_OP; "
        "END $$"
    ))
    op.execute(sa.text(
        "CREATE TRIGGER trg_decision_trace_sources_append_only "
        "BEFORE UPDATE OR DELETE ON public.decision_trace_sources "
        "FOR EACH ROW EXECUTE FUNCTION public.reject_decision_trace_source_change()"
    ))
    op.execute(sa.text(
        "CREATE TRIGGER trg_decision_trace_sources_no_truncate "
        "BEFORE TRUNCATE ON public.decision_trace_sources "
        "FOR EACH STATEMENT EXECUTE FUNCTION public.reject_decision_trace_source_change()"
    ))

    for table in (
        "frameworks",
        "framework_versions",
        "kb_versions",
        "interview_blocks",
        "assessment_modules",
        "questions",
        "assessment_participants",
        "assessment_sessions",
        "session_participants",
        "interview_turns",
        "decision_trace_sources",
    ):
        op.execute(sa.text(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY'))


def downgrade() -> None:
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_decision_trace_sources_no_truncate ON public.decision_trace_sources"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_decision_trace_sources_append_only ON public.decision_trace_sources"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS public.reject_decision_trace_source_change()"))
    op.drop_index("ix_decision_trace_sources_trace_id", table_name="decision_trace_sources")
    op.drop_table("decision_trace_sources")
    op.drop_constraint("uq_decision_traces_org_id", "decision_traces", type_="unique")

    for table in (
        "interview_turns",
        "session_participants",
        "assessment_sessions",
        "assessment_participants",
        "questions",
        "assessment_modules",
        "interview_blocks",
        "kb_versions",
        "framework_versions",
        "frameworks",
    ):
        op.drop_table(table)

    bind = op.get_bind()
    for enum_type in (
        postgresql.ENUM(*KB_VERSION_STATUS_VALUES, name="kb_version_status"),
        postgresql.ENUM(*TURN_TYPE_VALUES, name="turn_type"),
        postgresql.ENUM(*TURN_SPEAKER_VALUES, name="turn_speaker"),
        postgresql.ENUM(*SESSION_TYPE_VALUES, name="session_type"),
        postgresql.ENUM(*ACTOR_TYPE_VALUES, name="actor_type"),
        postgresql.ENUM(*SOURCE_TYPE_VALUES, name="source_type"),
    ):
        enum_type.drop(bind, checkfirst=True)

    # Keep agentic_grc_private and its checkpointer state. Checkpoint retention and deletion
    # policy is intentionally a governance gate before production-like data is processed.
