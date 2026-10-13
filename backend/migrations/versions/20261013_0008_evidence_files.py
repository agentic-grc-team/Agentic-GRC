"""Add evidence_files: metadata and extracted text of uploaded evidence documents.

Revision ID: 20261013_0008
Revises: 20261013_0007
Create Date: 2026-10-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '20261013_0008'
down_revision: Union[str, None] = '20261013_0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('evidence_files',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('assessment_id', sa.Uuid(), nullable=True),
        sa.Column('uploaded_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('stored_filename', sa.String(length=255), nullable=False),
        sa.Column('content_type', sa.String(length=255), nullable=True),
        sa.Column('file_extension', sa.String(length=10), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('extracted_text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(btrim(original_filename)) > 0", name=op.f('ck_evidence_files_filename_not_blank')),
        sa.CheckConstraint("file_extension IN ('.pdf', '.txt', '.docx', '.csv', '.xlsx')", name=op.f('ck_evidence_files_file_extension')),
        sa.CheckConstraint("size_bytes > 0 AND size_bytes <= 10485760", name=op.f('ck_evidence_files_size_bytes')),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name=op.f('ck_evidence_files_sha256_format')),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_evidence_files_organization_id_organizations')),
        sa.ForeignKeyConstraint(['uploaded_by_user_id'], ['users.id'], name=op.f('fk_evidence_files_uploaded_by_user_id_users'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id', 'assessment_id'], ['assessments.organization_id', 'assessments.id'], name='fk_evidence_files_assessment_same_org'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_evidence_files')),
        sa.UniqueConstraint('stored_filename', name=op.f('uq_evidence_files_stored_filename')),
        sa.UniqueConstraint('organization_id', 'id', name='uq_evidence_files_org_id')
    )
    op.create_index('ix_evidence_files_org_created', 'evidence_files', ['organization_id', 'created_at'], unique=False)
    op.create_index('ix_evidence_files_org_assessment', 'evidence_files', ['organization_id', 'assessment_id'], unique=False)
    op.execute(sa.text('ALTER TABLE public."evidence_files" ENABLE ROW LEVEL SECURITY'))


def downgrade() -> None:
    op.drop_index('ix_evidence_files_org_assessment', table_name='evidence_files')
    op.drop_index('ix_evidence_files_org_created', table_name='evidence_files')
    op.drop_table('evidence_files')
