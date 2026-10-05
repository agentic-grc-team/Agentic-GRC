from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Uuid,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("oidc_issuer", "oidc_subject", name="uq_users_oidc_identity"),
        CheckConstraint(
            "(oidc_issuer IS NULL AND oidc_subject IS NULL) OR "
            "(oidc_issuer IS NOT NULL AND oidc_subject IS NOT NULL)",
            name="oidc_identity_complete",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    oidc_issuer: Mapped[str | None] = mapped_column(String(512), nullable=True)
    oidc_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
    sector: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[str] = mapped_column(String(50), nullable=False)
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
        CheckConstraint("role IN ('administrator', 'consultant')", name="membership_role"),
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
        CheckConstraint("role IN ('administrator', 'consultant')", name="invitation_role"),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked', 'expired')", name="invitation_status"
        ),
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
