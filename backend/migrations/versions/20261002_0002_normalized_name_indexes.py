"""Use PostgreSQL btrim expressions for normalized-email/name indexes.

Revision ID: 20261002_0002
Revises: 20261002_0001
Create Date: 2026-10-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261002_0002"
down_revision: Union[str, None] = "20261002_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("uq_pending_invitation_organization_email", table_name="organization_invitations")
    op.drop_index("ix_organizations_name_normalized", table_name="organizations")
    op.drop_index("uq_users_email_normalized", table_name="users")

    op.create_index(
        "uq_users_email_normalized",
        "users",
        [sa.text("lower(btrim(email))")],
        unique=True,
    )
    op.create_index(
        "ix_organizations_name_normalized",
        "organizations",
        [sa.text("lower(btrim(name))")],
        unique=False,
    )
    op.create_index(
        "uq_pending_invitation_organization_email",
        "organization_invitations",
        ["organization_id", sa.text("lower(btrim(email))")],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("uq_pending_invitation_organization_email", table_name="organization_invitations")
    op.drop_index("ix_organizations_name_normalized", table_name="organizations")
    op.drop_index("uq_users_email_normalized", table_name="users")

    op.create_index(
        "uq_users_email_normalized",
        "users",
        [sa.text("lower(trim(email))")],
        unique=True,
    )
    op.create_index(
        "ix_organizations_name_normalized",
        "organizations",
        [sa.text("lower(trim(name))")],
        unique=False,
    )
    op.create_index(
        "uq_pending_invitation_organization_email",
        "organization_invitations",
        ["organization_id", sa.text("lower(trim(email))")],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
