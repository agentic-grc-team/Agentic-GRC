"""Initial provisional organization and membership schema.

Revision ID: 20261002_0001
Revises:
Create Date: 2026-10-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261002_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    op.create_index(
        "uq_users_email_normalized",
        "users",
        [sa.text("lower(trim(email))")],
        unique=True,
    )

    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sector", sa.String(length=100), nullable=False),
        sa.Column("size", sa.String(length=50), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("duplicate_of_organization_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("duplicate_name_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duplicate_name_confirmed_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "(duplicate_of_organization_id IS NULL "
            "AND duplicate_name_confirmed_at IS NULL) OR "
            "(duplicate_of_organization_id IS NOT NULL "
            "AND duplicate_name_confirmed_at IS NOT NULL)",
            name="duplicate_confirmation_complete",
        ),
        sa.CheckConstraint(
            "duplicate_of_organization_id IS NULL OR duplicate_of_organization_id <> id",
            name="not_own_duplicate",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], name="fk_organizations_created_by_user_id_users", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["duplicate_name_confirmed_by_user_id"],
            ["users.id"],
            name="fk_organizations_duplicate_name_confirmed_by_user_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["duplicate_of_organization_id"],
            ["organizations.id"],
            name="fk_organizations_duplicate_of_organization_id_organizations",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_organizations"),
    )
    op.create_index(
        "ix_organizations_name_normalized",
        "organizations",
        [sa.text("lower(trim(name))")],
        unique=False,
    )

    op.create_table(
        "organization_memberships",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=32), server_default="consultant", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role IN ('administrator', 'consultant')", name="membership_role"),
        sa.CheckConstraint("status IN ('active', 'suspended')", name="membership_status"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_organization_memberships_organization_id_organizations", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name="fk_organization_memberships_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_organization_memberships"),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_membership_organization_user"),
    )

    op.create_table(
        "organization_invitations",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=32), server_default="consultant", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=True),
        sa.Column("invited_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("accepted_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role IN ('administrator', 'consultant')", name="invitation_role"),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked', 'expired')",
            name="invitation_status",
        ),
        sa.ForeignKeyConstraint(
            ["accepted_by_user_id"], ["users.id"],
            name="fk_organization_invitations_accepted_by_user_id_users", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_user_id"], ["users.id"],
            name="fk_organization_invitations_invited_by_user_id_users", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_organization_invitations_organization_id_organizations", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_organization_invitations"),
    )
    op.create_index(
        "uq_pending_invitation_organization_email",
        "organization_invitations",
        ["organization_id", sa.text("lower(trim(email))")],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "uq_organization_invitation_token_hash",
        "organization_invitations",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_organization_invitation_token_hash", table_name="organization_invitations")
    op.drop_index("uq_pending_invitation_organization_email", table_name="organization_invitations")
    op.drop_table("organization_invitations")
    op.drop_table("organization_memberships")
    op.drop_index("ix_organizations_name_normalized", table_name="organizations")
    op.drop_table("organizations")
    op.drop_index("uq_users_email_normalized", table_name="users")
    op.drop_table("users")
