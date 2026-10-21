from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    Uuid,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), primary_key=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    is_platform_admin: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    memberships: Mapped[list[OrganizationMembership]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    sent_invitations: Mapped[list[OrganizationInvitation]] = relationship(
        back_populates="invited_by", foreign_keys="OrganizationInvitation.invited_by_user_id"
    )
    accepted_invitations: Mapped[list[OrganizationInvitation]] = relationship(
        back_populates="accepted_by", foreign_keys="OrganizationInvitation.accepted_by_user_id"
    )
    created_organizations: Mapped[list[Organization]] = relationship(
        back_populates="created_by", foreign_keys="Organization.created_by_user_id"
    )
    confirmed_duplicate_organizations: Mapped[list[Organization]] = relationship(
        back_populates="duplicate_name_confirmed_by",
        foreign_keys="Organization.duplicate_name_confirmed_by_user_id",
    )


Index(
    "uq_users_email_normalized",
    func.lower(func.btrim(User.email)),
    unique=True,
)


class IndustrySector(Base):
    __tablename__ = "industry_sectors"

    code: Mapped[str] = mapped_column(String(50), primary_key=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    organizations: Mapped[list[Organization]] = relationship(back_populates="industry_sector")


class OrganizationSize(Base):
    __tablename__ = "organization_sizes"

    code: Mapped[str] = mapped_column(String(30), primary_key=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    organizations: Mapped[list[Organization]] = relationship(back_populates="organization_size")


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint(
            "(duplicate_of_organization_id IS NULL "
            "AND duplicate_name_confirmed_at IS NULL) OR "
            "(duplicate_of_organization_id IS NOT NULL "
            "AND duplicate_name_confirmed_at IS NOT NULL)",
            name="duplicate_confirmation_complete",
        ),
        CheckConstraint(
            "duplicate_of_organization_id IS NULL OR duplicate_of_organization_id <> id",
            name="not_own_duplicate",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sector_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("industry_sectors.code"), nullable=False
    )
    size_code: Mapped[str] = mapped_column(
        String(30), ForeignKey("organization_sizes.code"), nullable=False
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    duplicate_of_organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=True
    )
    duplicate_name_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duplicate_name_confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    created_by: Mapped[User | None] = relationship(
        back_populates="created_organizations", foreign_keys=[created_by_user_id]
    )
    industry_sector: Mapped[IndustrySector] = relationship(back_populates="organizations")
    organization_size: Mapped[OrganizationSize] = relationship(back_populates="organizations")
    duplicate_name_confirmed_by: Mapped[User | None] = relationship(
        back_populates="confirmed_duplicate_organizations",
        foreign_keys=[duplicate_name_confirmed_by_user_id],
    )
    memberships: Mapped[list[OrganizationMembership]] = relationship(
        back_populates="organization", cascade="all, delete-orphan", passive_deletes=True
    )
    invitations: Mapped[list[OrganizationInvitation]] = relationship(
        back_populates="organization", cascade="all, delete-orphan", passive_deletes=True
    )


Index(
    "ix_organizations_name_normalized",
    func.lower(func.btrim(Organization.name)),
)


class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_membership_organization_user"),
        CheckConstraint(
            "role IN ('administrator', 'consultant', 'representative')", name="membership_role"
        ),
        CheckConstraint("status IN ('active', 'suspended')", name="membership_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="consultant", server_default="consultant")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    organization: Mapped[Organization] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")


class OrganizationInvitation(Base):
    __tablename__ = "organization_invitations"
    __table_args__ = (
        CheckConstraint(
            "role IN ('administrator', 'consultant', 'representative')", name="invitation_role"
        ),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked', 'expired')", name="invitation_status"
        ),
        CheckConstraint(
            "status <> 'accepted' OR (accepted_at IS NOT NULL AND accepted_by_user_id IS NOT NULL)",
            name="invitation_accepted_complete",
        ),
        CheckConstraint(
            "status <> 'revoked' OR revoked_at IS NOT NULL", name="invitation_revoked_complete"
        ),
        CheckConstraint("expires_at > created_at", name="invitation_expiry_after_creation"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="consultant", server_default="consultant")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", server_default="pending")
    token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    invited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    accepted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    organization: Mapped[Organization] = relationship(back_populates="invitations")
    invited_by: Mapped[User | None] = relationship(
        back_populates="sent_invitations", foreign_keys=[invited_by_user_id]
    )
    accepted_by: Mapped[User | None] = relationship(
        back_populates="accepted_invitations", foreign_keys=[accepted_by_user_id]
    )


Index(
    "uq_pending_invitation_organization_email",
    OrganizationInvitation.organization_id,
    func.lower(func.btrim(OrganizationInvitation.email)),
    unique=True,
    postgresql_where=text("status = 'pending'"),
)
Index(
    "uq_organization_invitation_token_hash",
    OrganizationInvitation.token_hash,
    unique=True,
)


DECISION_TYPES = (
    "answer_interpreted",
    "evidence_requested",
    "evidence_extracted",
    "evidence_validated",
    "mapping_assigned",
    "status_assessed",
    "maturity_assessed",
    "contradiction_detected",
    "finding_generated",
    "human_review",
)
ACTOR_TYPES = ("agent", "assessed_org_representative", "aligo_consultant")
EVIDENCE_NATURES = ("intent", "implementation", "attestation")
REVIEW_OUTCOMES = ("accepted", "modified", "rejected")

# Same values as app.schemas.decision_trace.CONTROL_STATUSES (a test checks they stay equal).
CONTROL_STATUSES = ("implemented", "partially_implemented", "not_implemented", "not_applicable", "not_assessed")
ASSESSMENT_STATUSES = ("draft", "in_progress", "awaiting_review", "completed")
RESULT_AUTHORS = ("agent", "aligo_consultant")   # the assessed organization never authors a result (schema v0.3)
CSF_CODE_REGEX = r"^(GV|ID|PR|DE|RS|RC)\.[A-Z]{2}-[0-9]{2}$"
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

ACTOR_TYPE_ENUM = SqlEnum(*ACTOR_TYPE_VALUES, name="actor_type")
SESSION_TYPE_ENUM = SqlEnum(*SESSION_TYPE_VALUES, name="session_type")
TURN_SPEAKER_ENUM = SqlEnum(*TURN_SPEAKER_VALUES, name="turn_speaker")
TURN_TYPE_ENUM = SqlEnum(*TURN_TYPE_VALUES, name="turn_type")
KB_VERSION_STATUS_ENUM = SqlEnum(*KB_VERSION_STATUS_VALUES, name="kb_version_status")
SOURCE_TYPE_ENUM = SqlEnum(*SOURCE_TYPE_VALUES, name="source_type")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


class DecisionTraceRecord(Base):
    """Append-only reasoning trace (AGRC-15). See docs/design/trace-schema.md v0.2."""

    __tablename__ = "decision_traces"
    __table_args__ = (
        CheckConstraint(_in_list("decision_type", DECISION_TYPES), name="decision_type"),
        CheckConstraint(_in_list("actor_type", ACTOR_TYPES), name="actor_type"),
        CheckConstraint(
            "evidence_nature IS NULL OR " + _in_list("evidence_nature", EVIDENCE_NATURES),
            name="evidence_nature",
        ),
        CheckConstraint(
            "review_outcome IS NULL OR " + _in_list("review_outcome", REVIEW_OUTCOMES),
            name="review_outcome",
        ),
        CheckConstraint("jsonb_typeof(sources) = 'array'", name="sources_array"),
        CheckConstraint("jsonb_typeof(output) = 'object'", name="output_object"),
        CheckConstraint("confidence IS NULL OR confidence BETWEEN 0 AND 1", name="confidence_range"),
        CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="latency_non_negative"),
        CheckConstraint(
            "actor_type <> 'agent' OR (prompt_id IS NOT NULL AND prompt_version IS NOT NULL "
            "AND jsonb_array_length(sources) >= 1)",
            name="agent_complete",
        ),
        CheckConstraint(
            "actor_type <> 'agent' OR prompt_id LIKE 'rule:%' OR model_name IS NOT NULL",
            name="llm_has_model",
        ),
        CheckConstraint(
            "decision_type <> 'human_review' OR (reviews_trace_id IS NOT NULL AND review_outcome IS NOT NULL)",
            name="review_complete",
        ),
        CheckConstraint(
            "decision_type <> 'human_review' OR actor_type <> 'agent'", name="review_by_human"
        ),
        CheckConstraint(
            "(actor_type = 'agent') = (actor_user_id IS NULL)", name="actor_user_matches_type"
        ),
        # A review or a replacement must point to a trace of the same organization and assessment.
        UniqueConstraint("organization_id", "assessment_id", "id", name="uq_decision_traces_org_assessment_id"),
        UniqueConstraint("organization_id", "id", name="uq_decision_traces_org_id"),
        ForeignKeyConstraint(
            ["organization_id", "assessment_id", "reviews_trace_id"],
            ["decision_traces.organization_id", "decision_traces.assessment_id", "decision_traces.id"],
            name="fk_decision_traces_reviews_same_assessment",
        ),
        ForeignKeyConstraint(
            ["organization_id", "assessment_id", "supersedes_trace_id"],
            ["decision_traces.organization_id", "decision_traces.assessment_id", "decision_traces.id"],
            name="fk_decision_traces_supersedes_same_assessment",
        ),
        ForeignKeyConstraint(
            ["organization_id", "assessment_id"],
            ["assessments.organization_id", "assessments.id"],
            name="fk_decision_traces_assessment_same_org",
        ),
        Index("ix_decision_traces_org_assessment", "organization_id", "assessment_id", "created_at"),
        Index("ix_decision_traces_control_ids", "control_ids", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    # Composite FK to assessments (migration 0007): a trace can only point to an assessment of the same organization.
    assessment_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    # clock_timestamp(), not now(): now() is the same for every row in one transaction,
    # so several decisions saved together would lose their order.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )

    decision_type: Mapped[str] = mapped_column(String(32), nullable=False)
    control_ids: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    module: Mapped[str | None] = mapped_column(String(100), nullable=True)

    sources: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    evidence_nature: Mapped[str | None] = mapped_column(String(16), nullable=True)

    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    kb_version: Mapped[str] = mapped_column(String(50), nullable=False)

    output: Mapped[dict] = mapped_column(JSONB, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    requires_human_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fallback_used: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    reviews_trace_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    review_outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)
    supersedes_trace_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )


class DecisionTraceSourceRecord(Base):
    __tablename__ = "decision_trace_sources"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "trace_id"],
            ["decision_traces.organization_id", "decision_traces.id"],
            name="fk_decision_trace_sources_trace_same_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "interview_turn_id"],
            ["interview_turns.organization_id", "interview_turns.id"],
            name="fk_decision_trace_sources_turn_same_org",
        ),
        CheckConstraint(
            "num_nonnulls(interview_turn_id, document_chunk_id, configuration_item_id, prior_phase_finding_id) = 1",
            name="one_reference",
        ),
        CheckConstraint(
            "(source_type = 'interview_turn') = (interview_turn_id IS NOT NULL)",
            name="type_turn",
        ),
        CheckConstraint(
            "(source_type = 'document_span') = (document_chunk_id IS NOT NULL)",
            name="type_document",
        ),
        CheckConstraint(
            "(source_type = 'tenant_configuration') = (configuration_item_id IS NOT NULL)",
            name="type_configuration",
        ),
        CheckConstraint(
            "(source_type = 'prior_phase_evidence') = (prior_phase_finding_id IS NOT NULL)",
            name="type_prior_phase",
        ),
        UniqueConstraint("trace_id", "interview_turn_id", name="uq_trace_source_turn"),
        Index("ix_decision_trace_sources_trace_id", "trace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    trace_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source_type: Mapped[str] = mapped_column(SOURCE_TYPE_ENUM, nullable=False)
    interview_turn_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    document_chunk_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    configuration_item_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    prior_phase_finding_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)


class Assessment(Base):
    """An assessment of one organization against a cybersecurity framework (AGRC-61)."""

    __tablename__ = "assessments"
    __table_args__ = (
        CheckConstraint(_in_list("status", ASSESSMENT_STATUSES), name="status"),
        CheckConstraint("length(btrim(title)) > 0", name="title_not_blank"),
        CheckConstraint("status <> 'completed' OR completed_at IS NOT NULL", name="completed_at"),
        CheckConstraint(
            "completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at",
            name="dates_order",
        ),
        UniqueConstraint("organization_id", "id", name="uq_assessments_org_id"),
        Index("ix_assessments_org_created", "organization_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    framework_code: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="NIST-CSF"
    )
    framework_version: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="2.0"
    )
    kb_version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="draft"
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Framework(Base):
    __tablename__ = "frameworks"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FrameworkVersion(Base):
    __tablename__ = "framework_versions"
    __table_args__ = (UniqueConstraint("framework_id", "version", name="uq_framework_versions_framework_version"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    framework_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("frameworks.id"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(30), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class KBVersion(Base):
    __tablename__ = "kb_versions"
    __table_args__ = (
        CheckConstraint("status = 'draft' OR published_at IS NOT NULL", name="published_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    framework_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("framework_versions.id"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        KB_VERSION_STATUS_ENUM, nullable=False, server_default="draft"
    )
    is_provisional: Mapped[bool] = mapped_column(nullable=False, server_default="true")
    decision_record_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class InterviewBlock(Base):
    __tablename__ = "interview_blocks"
    __table_args__ = (
        UniqueConstraint("kb_version_id", "code", name="uq_interview_blocks_kb_version_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    kb_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("kb_versions.id"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(5), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    audience: Mapped[str] = mapped_column(Text, nullable=False)
    estimated_minutes: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")


class AssessmentModule(Base):
    __tablename__ = "assessment_modules"
    __table_args__ = (
        UniqueConstraint("kb_version_id", "code", name="uq_assessment_modules_kb_version_code"),
        Index("ix_assessment_modules_block_id", "block_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    kb_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("kb_versions.id"), nullable=False
    )
    block_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("interview_blocks.id"), nullable=True
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("module_id", "code", name="uq_questions_module_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    module_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assessment_modules.id"), nullable=False
    )
    # Optional knowledge-base references are connected when their catalog tables are adopted.
    statement_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    remediation_template_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    language_code: Mapped[str] = mapped_column(String(10), nullable=False, server_default="en")
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")


class AssessmentParticipant(Base):
    __tablename__ = "assessment_participants"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "assessment_id"],
            ["assessments.organization_id", "assessments.id"],
            name="fk_assessment_participants_assessment_same_org",
        ),
        CheckConstraint("participant_type <> 'agent'", name="human"),
        UniqueConstraint("organization_id", "id", name="uq_assessment_participants_tenant"),
        Index("ix_assessment_participants_assessment_id", "assessment_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    assessment_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    participant_type: Mapped[str] = mapped_column(ACTOR_TYPE_ENUM, nullable=False)
    role_title: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AssessmentSession(Base):
    __tablename__ = "assessment_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "assessment_id"],
            ["assessments.organization_id", "assessments.id"],
            name="fk_assessment_sessions_assessment_same_org",
        ),
        CheckConstraint(
            "(session_type = 'block') = (block_id IS NOT NULL)", name="block"
        ),
        CheckConstraint(
            "ended_at IS NULL OR started_at IS NULL OR ended_at >= started_at",
            name="dates",
        ),
        UniqueConstraint("organization_id", "id", name="uq_assessment_sessions_tenant"),
        Index("ix_assessment_sessions_assessment_id", "assessment_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    assessment_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    session_type: Mapped[str] = mapped_column(SESSION_TYPE_ENUM, nullable=False)
    block_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("interview_blocks.id"), nullable=True
    )
    facilitator_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resume_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class SessionParticipant(Base):
    __tablename__ = "session_participants"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "session_id"],
            ["assessment_sessions.organization_id", "assessment_sessions.id"],
            name="fk_session_participants_session_same_org",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "participant_id"],
            ["assessment_participants.organization_id", "assessment_participants.id"],
            name="fk_session_participants_participant_same_org",
        ),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    participant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class InterviewTurn(Base):
    __tablename__ = "interview_turns"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "session_id"],
            ["assessment_sessions.organization_id", "assessment_sessions.id"],
            name="fk_interview_turns_session_same_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "participant_id"],
            ["assessment_participants.organization_id", "assessment_participants.id"],
            name="fk_interview_turns_participant_same_org",
        ),
        ForeignKeyConstraint(
            ["organization_id", "replies_to_turn_id"],
            ["interview_turns.organization_id", "interview_turns.id"],
            name="fk_interview_turns_reply_same_org",
        ),
        CheckConstraint(
            "(speaker = 'participant') = (participant_id IS NOT NULL)", name="participant"
        ),
        UniqueConstraint("session_id", "sequence_no", name="uq_interview_turns_session_sequence"),
        UniqueConstraint("organization_id", "id", name="uq_interview_turns_tenant"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker: Mapped[str] = mapped_column(TURN_SPEAKER_ENUM, nullable=False)
    participant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    turn_type: Mapped[str] = mapped_column(TURN_TYPE_ENUM, nullable=False)
    question_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("questions.id"), nullable=True
    )
    replies_to_turn_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    language_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AssessmentControl(Base):
    """A framework control / subcategory in scope of an assessment (0007)."""

    __tablename__ = "assessment_controls"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "assessment_id"],
            ["assessments.organization_id", "assessments.id"],
            name="fk_assessment_controls_assessment_same_org",
        ),
        CheckConstraint(f"control_code ~ '{CSF_CODE_REGEX}'", name="control_code_format"),
        CheckConstraint("length(btrim(control_title)) > 0", name="title_not_blank"),
        CheckConstraint(
            "in_scope OR (scope_rationale IS NOT NULL AND length(btrim(scope_rationale)) > 0)",
            name="scope_rationale",
        ),
        UniqueConstraint("assessment_id", "control_code", name="uq_assessment_controls_assessment_code"),
        UniqueConstraint("organization_id", "assessment_id", "id", name="uq_assessment_controls_org_assessment_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    assessment_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    control_code: Mapped[str] = mapped_column(String(20), nullable=False)
    control_title: Mapped[str] = mapped_column(String(500), nullable=False)
    in_scope: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    scope_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# Nullable columns (based_on_result_id, trace_id) skip the FK check when NULL under PostgreSQL's default MATCH SIMPLE.
class ControlResult(Base):
    """Immutable version of the result of one control (0007)."""

    __tablename__ = "control_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "assessment_id", "assessment_control_id"],
            ["assessment_controls.organization_id", "assessment_controls.assessment_id", "assessment_controls.id"],
            name="fk_control_results_control_same_assessment",
        ),
        ForeignKeyConstraint(
            ["organization_id", "assessment_id", "based_on_result_id"],
            ["control_results.organization_id", "control_results.assessment_id", "control_results.id"],
            name="fk_control_results_based_on_same_assessment",
        ),
        ForeignKeyConstraint(
            ["organization_id", "assessment_id", "trace_id"],
            ["decision_traces.organization_id", "decision_traces.assessment_id", "decision_traces.id"],
            name="fk_control_results_trace_same_assessment",
        ),
        UniqueConstraint("assessment_control_id", "version_no", name="uq_control_results_control_version"),
        UniqueConstraint("organization_id", "assessment_id", "id", name="uq_control_results_org_assessment_id"),
        CheckConstraint("version_no >= 1", name="version_positive"),
        CheckConstraint(_in_list("author_actor", RESULT_AUTHORS), name="author_actor"),
        CheckConstraint(
            "(author_actor = 'agent') = (author_user_id IS NULL)",
            name="author_user_matches_actor",
        ),
        CheckConstraint(_in_list("control_status", CONTROL_STATUSES), name="control_status"),
        CheckConstraint("length(btrim(explanation)) > 0", name="explanation_not_blank"),
        CheckConstraint(
            "control_status <> 'not_applicable' OR (justification IS NOT NULL AND length(btrim(justification)) > 0)",
            name="not_applicable_justified",
        ),
        CheckConstraint(
            "control_status <> 'not_assessed' OR (not_assessed_reason IS NOT NULL AND length(btrim(not_assessed_reason)) > 0)",
            name="not_assessed_reason",
        ),
        CheckConstraint(
            "maturity_current IS NULL OR maturity_current BETWEEN 1 AND 5",
            name="maturity_current_range",
        ),
        CheckConstraint(
            "maturity_target IS NULL OR maturity_target BETWEEN 1 AND 5",
            name="maturity_target_range",
        ),
        CheckConstraint("confidence IS NULL OR confidence BETWEEN 0 AND 1", name="confidence_range"),
        CheckConstraint("jsonb_typeof(evidence_refs) = 'array'", name="evidence_refs_array"),
        CheckConstraint(
            "based_on_result_id IS NULL OR based_on_result_id <> id",
            name="not_based_on_self",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    assessment_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    assessment_control_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    based_on_result_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    author_actor: Mapped[str] = mapped_column(String(32), nullable=False)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    control_status: Mapped[str] = mapped_column(String(32), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    not_assessed_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    maturity_current: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    maturity_target: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    requires_human_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    evidence_pending: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    evidence_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_refs: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    trace_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


# Domain rules (only agent versions reviewed, resulting version consultant-authored with higher version_no) enforced in service (AGRC-52).
class ControlResultReview(Base):
    """Review of an agent-authored control result version (0007)."""

    __tablename__ = "control_result_reviews"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "assessment_id", "control_result_id"],
            ["control_results.organization_id", "control_results.assessment_id", "control_results.id"],
            name="fk_control_result_reviews_result_same_assessment",
        ),
        ForeignKeyConstraint(
            ["organization_id", "assessment_id", "resulting_result_id"],
            ["control_results.organization_id", "control_results.assessment_id", "control_results.id"],
            name="fk_control_result_reviews_resulting_same_assessment",
        ),
        ForeignKeyConstraint(
            ["organization_id", "assessment_id", "review_trace_id"],
            ["decision_traces.organization_id", "decision_traces.assessment_id", "decision_traces.id"],
            name="fk_control_result_reviews_trace_same_assessment",
        ),
        UniqueConstraint("control_result_id", name="uq_control_result_reviews_result"),
        CheckConstraint(_in_list("outcome", REVIEW_OUTCOMES), name="outcome"),
        CheckConstraint(
            "(outcome = 'modified') = (resulting_result_id IS NOT NULL)",
            name="modified_has_result",
        ),
        CheckConstraint(
            "resulting_result_id IS NULL OR resulting_result_id <> control_result_id",
            name="resulting_differs",
        ),
        CheckConstraint(
            "outcome = 'accepted' OR length(btrim(comment)) > 0",
            name="comment_required",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    assessment_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    control_result_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    resulting_result_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    comment: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    reviewed_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    review_trace_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )


EVIDENCE_MAX_BYTES = 10 * 1024 * 1024


class EvidenceFile(Base):
    """Metadata and extracted text of one uploaded evidence document (0008)."""

    __tablename__ = "evidence_files"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "assessment_id"],
            ["assessments.organization_id", "assessments.id"],
            name="fk_evidence_files_assessment_same_org",
        ),
        CheckConstraint("length(btrim(original_filename)) > 0", name="filename_not_blank"),
        CheckConstraint(
            "file_extension IN ('.pdf', '.txt', '.docx', '.csv', '.xlsx')",
            name="file_extension",
        ),
        CheckConstraint(
            f"size_bytes > 0 AND size_bytes <= {EVIDENCE_MAX_BYTES}",
            name="size_bytes",
        ),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256_format"),
        UniqueConstraint("organization_id", "id", name="uq_evidence_files_org_id"),
        Index("ix_evidence_files_org_created", "organization_id", "created_at"),
        Index("ix_evidence_files_org_assessment", "organization_id", "assessment_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_extension: Mapped[str] = mapped_column(String(10), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# The evidence file's own assessment (when it has one) must match the control's assessment; checked in the service.
class EvidenceControlLink(Base):
    """Links one uploaded evidence file to one control of an assessment (0009)."""

    __tablename__ = "evidence_control_links"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "assessment_id", "assessment_control_id"],
            ["assessment_controls.organization_id", "assessment_controls.assessment_id", "assessment_controls.id"],
            name="fk_evidence_control_links_control_same_assessment",
        ),
        ForeignKeyConstraint(
            ["organization_id", "evidence_file_id"],
            ["evidence_files.organization_id", "evidence_files.id"],
            name="fk_evidence_control_links_evidence_same_org",
        ),
        UniqueConstraint(
            "assessment_control_id", "evidence_file_id", name="uq_evidence_control_links_control_evidence"
        ),
        Index("ix_evidence_control_links_org_evidence", "organization_id", "evidence_file_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    assessment_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    assessment_control_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    evidence_file_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    linked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

