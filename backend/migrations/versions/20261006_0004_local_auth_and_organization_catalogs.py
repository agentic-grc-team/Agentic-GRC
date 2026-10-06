"""Add local authentication fields, role support, and organization catalogs.

Revision ID: 20261006_0004
Revises: 20261002_0003
Create Date: 2026-10-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261006_0004"
down_revision: Union[str, None] = "20261002_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _catalog_identity(expression: str, fallback: str) -> str:
    return f"coalesce(nullif(lower(btrim({expression})), ''), '{fallback}')"


def _catalog_code(expression: str, fallback: str, maximum_length: int) -> str:
    slug_length = maximum_length - 9
    identity = _catalog_identity(expression, fallback)
    slug = (
        "coalesce(nullif(trim(both '-' from regexp_replace("
        f"{identity}, '[^a-z0-9]+', '-', 'g')), ''), '{fallback}')"
    )
    return (
        f"left({slug}, {slug_length}) || '_' "
        f"|| substr(md5({identity}), 1, 8)"
    )


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users",
        sa.Column("is_platform_admin", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("users", sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "industry_sectors",
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("code", name="pk_industry_sectors"),
    )
    op.create_table(
        "organization_sizes",
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("code", name="pk_organization_sizes"),
    )
    op.execute(
        sa.text("INSERT INTO industry_sectors (code, label) VALUES ('other', 'Other / not specified')")
    )
    op.execute(
        sa.text("INSERT INTO organization_sizes (code, label) VALUES ('unknown', 'Not specified')")
    )

    sector_code = _catalog_code("sector", "sector", 50)
    size_code = _catalog_code("size", "size", 30)
    sector_identity = _catalog_identity("sector", "sector")
    size_identity = _catalog_identity("size", "size")
    op.execute(
        sa.text(
            "INSERT INTO industry_sectors (code, label) "
            f"SELECT {sector_code}, left(coalesce(nullif(min(btrim(sector)), ''), 'Unspecified'), 100) "
            f"FROM organizations GROUP BY {sector_identity}"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO organization_sizes (code, label) "
            f"SELECT {size_code}, left(coalesce(nullif(min(btrim(size)), ''), 'Unspecified'), 100) "
            f"FROM organizations GROUP BY {size_identity}"
        )
    )

    op.add_column("organizations", sa.Column("sector_code", sa.String(length=50), nullable=True))
    op.add_column("organizations", sa.Column("size_code", sa.String(length=30), nullable=True))
    op.execute(
        sa.text(
            "UPDATE organizations AS organization "
            f"SET sector_code = {sector_code} "
            "WHERE sector_code IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE organizations AS organization "
            f"SET size_code = {size_code} "
            "WHERE size_code IS NULL"
        )
    )
    op.alter_column("organizations", "sector_code", nullable=False)
    op.alter_column("organizations", "size_code", nullable=False)
    op.create_foreign_key(
        "fk_organizations_sector_code_industry_sectors",
        "organizations",
        "industry_sectors",
        ["sector_code"],
        ["code"],
    )
    op.create_foreign_key(
        "fk_organizations_size_code_organization_sizes",
        "organizations",
        "organization_sizes",
        ["size_code"],
        ["code"],
    )
    op.drop_column("organizations", "sector")
    op.drop_column("organizations", "size")

    op.drop_constraint("membership_role", "organization_memberships", type_="check")
    op.create_check_constraint(
        "membership_role",
        "organization_memberships",
        "role IN ('administrator', 'consultant', 'representative')",
    )
    op.drop_constraint("invitation_role", "organization_invitations", type_="check")
    op.create_check_constraint(
        "invitation_role",
        "organization_invitations",
        "role IN ('administrator', 'consultant', 'representative')",
    )
    op.create_check_constraint(
        "invitation_accepted_complete",
        "organization_invitations",
        "status <> 'accepted' OR (accepted_at IS NOT NULL AND accepted_by_user_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "invitation_revoked_complete",
        "organization_invitations",
        "status <> 'revoked' OR revoked_at IS NOT NULL",
    )
    op.create_check_constraint(
        "invitation_expiry_after_creation",
        "organization_invitations",
        "expires_at > created_at",
    )


def downgrade() -> None:
    op.drop_constraint(
        "invitation_expiry_after_creation", "organization_invitations", type_="check"
    )
    op.drop_constraint(
        "invitation_revoked_complete", "organization_invitations", type_="check"
    )
    op.drop_constraint(
        "invitation_accepted_complete", "organization_invitations", type_="check"
    )
    op.drop_constraint("invitation_role", "organization_invitations", type_="check")
    op.create_check_constraint(
        "invitation_role",
        "organization_invitations",
        "role IN ('administrator', 'consultant')",
    )
    op.drop_constraint("membership_role", "organization_memberships", type_="check")
    op.create_check_constraint(
        "membership_role",
        "organization_memberships",
        "role IN ('administrator', 'consultant')",
    )

    op.add_column("organizations", sa.Column("sector", sa.String(length=100), nullable=True))
    op.add_column("organizations", sa.Column("size", sa.String(length=50), nullable=True))
    op.execute(
        sa.text(
            "UPDATE organizations AS organization "
            "SET sector = industry_sectors.label "
            "FROM industry_sectors WHERE industry_sectors.code = organization.sector_code"
        )
    )
    op.execute(
        sa.text(
            "UPDATE organizations AS organization "
            "SET size = organization_sizes.label "
            "FROM organization_sizes WHERE organization_sizes.code = organization.size_code"
        )
    )
    op.alter_column("organizations", "sector", nullable=False)
    op.alter_column("organizations", "size", nullable=False)
    op.drop_constraint("fk_organizations_size_code_organization_sizes", "organizations", type_="foreignkey")
    op.drop_constraint("fk_organizations_sector_code_industry_sectors", "organizations", type_="foreignkey")
    op.drop_column("organizations", "size_code")
    op.drop_column("organizations", "sector_code")
    op.drop_table("organization_sizes")
    op.drop_table("industry_sectors")

    op.drop_column("users", "deactivated_at")
    op.drop_column("users", "is_platform_admin")
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "password_hash")
