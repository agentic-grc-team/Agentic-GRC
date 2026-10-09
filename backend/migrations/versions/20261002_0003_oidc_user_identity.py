"""Store verified OIDC identity on platform users.

Revision ID: 20261002_0003
Revises: 20261002_0002
Create Date: 2026-10-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261002_0003"
down_revision: Union[str, None] = "20261002_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("oidc_issuer", sa.String(length=512), nullable=True))
    op.add_column("users", sa.Column("oidc_subject", sa.String(length=255), nullable=True))
    op.create_unique_constraint("uq_users_oidc_identity", "users", ["oidc_issuer", "oidc_subject"])
    op.create_check_constraint(
        "oidc_identity_complete",
        "users",
        "(oidc_issuer IS NULL AND oidc_subject IS NULL) OR "
        "(oidc_issuer IS NOT NULL AND oidc_subject IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("oidc_identity_complete", "users", type_="check")
    op.drop_constraint("uq_users_oidc_identity", "users", type_="unique")
    op.drop_column("users", "oidc_subject")
    op.drop_column("users", "oidc_issuer")
