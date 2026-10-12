from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
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
        Index("ix_decision_traces_org_assessment", "organization_id", "assessment_id", "created_at"),
        Index("ix_decision_traces_control_ids", "control_ids", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    # No foreign key yet: the assessments table does not exist (trace-schema.md, section 10).
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
