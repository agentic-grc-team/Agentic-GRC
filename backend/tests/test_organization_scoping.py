"""Every table that stores organization data must carry a non-null organization_id covered by a foreign key."""

import pytest

import app.db.models  # noqa: F401  (registers every model on Base.metadata)
from app.db.base import Base

# Identity and lookup tables hold no organization data.
TABLES_WITHOUT_ORGANIZATION_ID = {
    "auth.users",
    "users",
    "organizations",
    "industry_sectors",
    "organization_sizes",
}


def protected_tables():
    return [
        table
        for name, table in sorted(Base.metadata.tables.items())
        if name not in TABLES_WITHOUT_ORGANIZATION_ID
    ]


def foreign_key_column_names(table):
    return [
        {column.name for column in constraint.columns}
        for constraint in table.foreign_key_constraints
    ]


def test_exception_list_only_names_existing_tables():
    assert TABLES_WITHOUT_ORGANIZATION_ID <= set(Base.metadata.tables)


@pytest.mark.parametrize("table", protected_tables(), ids=lambda table: table.name)
def test_protected_table_has_non_null_organization_id(table):
    assert "organization_id" in table.c, f"{table.name} must have an organization_id column"
    assert not table.c.organization_id.nullable, f"{table.name}.organization_id must be NOT NULL"


@pytest.mark.parametrize("table", protected_tables(), ids=lambda table: table.name)
def test_protected_table_organization_id_is_covered_by_a_foreign_key(table):
    assert any(
        "organization_id" in columns for columns in foreign_key_column_names(table)
    ), f"{table.name}.organization_id must be part of a foreign key"


@pytest.mark.parametrize(
    "table",
    [table for table in protected_tables() if "assessment_id" in table.c],
    ids=lambda table: table.name,
)
def test_assessment_reference_cannot_cross_organizations(table):
    assert any(
        {"organization_id", "assessment_id"} <= columns
        for columns in foreign_key_column_names(table)
    ), f"{table.name} must reference assessments through (organization_id, assessment_id)"
