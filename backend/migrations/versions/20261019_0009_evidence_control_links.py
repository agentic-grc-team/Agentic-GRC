"""Add evidence_control_links: which evidence file supports which control of an assessment.

Revision ID: 20261019_0009
Revises: 20261013_0008
Create Date: 2026-10-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '20261019_0009'
down_revision: Union[str, None] = '20261013_0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('evidence_control_links',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('assessment_id', sa.Uuid(), nullable=False),
        sa.Column('assessment_control_id', sa.Uuid(), nullable=False),
        sa.Column('evidence_file_id', sa.Uuid(), nullable=False),
        sa.Column('linked_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['linked_by_user_id'], ['users.id'], name=op.f('fk_evidence_control_links_linked_by_user_id_users'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id', 'assessment_id', 'assessment_control_id'], ['assessment_controls.organization_id', 'assessment_controls.assessment_id', 'assessment_controls.id'], name='fk_evidence_control_links_control_same_assessment'),
        sa.ForeignKeyConstraint(['organization_id', 'evidence_file_id'], ['evidence_files.organization_id', 'evidence_files.id'], name='fk_evidence_control_links_evidence_same_org'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_evidence_control_links')),
        sa.UniqueConstraint('assessment_control_id', 'evidence_file_id', name='uq_evidence_control_links_control_evidence')
    )
    op.create_index('ix_evidence_control_links_org_evidence', 'evidence_control_links', ['organization_id', 'evidence_file_id'], unique=False)
    op.execute(sa.text('ALTER TABLE public."evidence_control_links" ENABLE ROW LEVEL SECURITY'))


def downgrade() -> None:
    op.drop_index('ix_evidence_control_links_org_evidence', table_name='evidence_control_links')
    op.drop_table('evidence_control_links')
