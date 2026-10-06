"""Use Supabase Auth identities for platform users.

Revision ID: 20261006_0005
Revises: 20261006_0004
Create Date: 2026-10-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261006_0005"
down_revision: Union[str, None] = "20261006_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_PUBLIC_TABLES = (
    "users",
    "organizations",
    "organization_memberships",
    "organization_invitations",
    "industry_sectors",
    "organization_sizes",
)


def upgrade() -> None:
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "IF to_regclass('auth.users') IS NULL THEN "
            "RAISE EXCEPTION 'Supabase Auth table auth.users is unavailable'; "
            "END IF; "
            "IF EXISTS (SELECT 1 FROM public.users AS app_user "
            "LEFT JOIN auth.users AS auth_user ON auth_user.id = app_user.id "
            "WHERE auth_user.id IS NULL) THEN "
            "RAISE EXCEPTION 'Existing public.users rows must be mapped to auth.users before this migration'; "
            "END IF; END $$"
        )
    )

    op.drop_constraint("oidc_identity_complete", "users", type_="check")
    op.drop_constraint("uq_users_oidc_identity", "users", type_="unique")
    op.drop_column("users", "oidc_subject")
    op.drop_column("users", "oidc_issuer")
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "password_hash")
    op.create_foreign_key(
        "fk_users_id_auth_users",
        "users",
        "users",
        ["id"],
        ["id"],
        source_schema="public",
        referent_schema="auth",
        ondelete="CASCADE",
    )

    for table_name in _PUBLIC_TABLES:
        op.execute(sa.text(f'ALTER TABLE public."{table_name}" ENABLE ROW LEVEL SECURITY'))


def downgrade() -> None:
    for table_name in _PUBLIC_TABLES:
        op.execute(sa.text(f'ALTER TABLE public."{table_name}" DISABLE ROW LEVEL SECURITY'))

    op.drop_constraint("fk_users_id_auth_users", "users", type_="foreignkey", schema="public")
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("oidc_issuer", sa.String(length=512), nullable=True))
    op.add_column("users", sa.Column("oidc_subject", sa.String(length=255), nullable=True))
    op.create_unique_constraint("uq_users_oidc_identity", "users", ["oidc_issuer", "oidc_subject"])
    op.create_check_constraint(
        "oidc_identity_complete",
        "users",
        "(oidc_issuer IS NULL AND oidc_subject IS NULL) OR "
        "(oidc_issuer IS NOT NULL AND oidc_subject IS NOT NULL)",
    )
