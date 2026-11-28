"""Add tenant_configuration_snapshots: dated reads of a Microsoft 365 tenant for an assessment.

Revision ID: 20261128_0012
Revises: 20261116_0011
Create Date: 2026-11-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '20261128_0012'
down_revision: Union[str, None] = '20261116_0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('tenant_configuration_snapshots',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('assessment_id', sa.Uuid(), nullable=False),
        sa.Column('collected_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.String(length=64), nullable=False),
        sa.Column('schema_version', sa.SmallInteger(), nullable=False),
        sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('collected_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("source IN ('microsoft_graph', 'sample')", name=op.f('ck_tenant_configuration_snapshots_source')),
        sa.CheckConstraint('length(btrim(tenant_id)) > 0', name=op.f('ck_tenant_configuration_snapshots_tenant_id_not_blank')),
        sa.CheckConstraint("jsonb_typeof(data) = 'object'", name=op.f('ck_tenant_configuration_snapshots_data_is_object')),
        sa.ForeignKeyConstraint(['collected_by_user_id'], ['users.id'], name=op.f('fk_tenant_configuration_snapshots_collected_by_user_id_users'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_tenant_configuration_snapshots_organization_id_organizations')),
        sa.ForeignKeyConstraint(['organization_id', 'assessment_id'], ['assessments.organization_id', 'assessments.id'], name='fk_tenant_configuration_snapshots_assessment_same_org'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_tenant_configuration_snapshots')),
        sa.UniqueConstraint('organization_id', 'id', name='uq_tenant_configuration_snapshots_org_id')
    )
    op.create_index('ix_tenant_configuration_snapshots_org_assessment_collected', 'tenant_configuration_snapshots', ['organization_id', 'assessment_id', 'collected_at'], unique=False)
    op.execute(sa.text('ALTER TABLE public."tenant_configuration_snapshots" ENABLE ROW LEVEL SECURITY'))


def downgrade() -> None:
    op.drop_index('ix_tenant_configuration_snapshots_org_assessment_collected', table_name='tenant_configuration_snapshots')
    op.drop_table('tenant_configuration_snapshots')
