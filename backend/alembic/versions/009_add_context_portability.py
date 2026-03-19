"""Add context portability job tracking tables

Revision ID: 009
Revises: 008
Create Date: 2026-03-18
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = '009'
down_revision: Union[str, None] = '008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Export job status enum
    export_status = sa.Enum(
        'pending', 'running', 'completed', 'failed',
        name='export_job_status',
    )
    export_status.create(op.get_bind(), checkfirst=True)

    # Import job status enum
    import_status = sa.Enum(
        'pending', 'running', 'importing', 're_embedding', 'completed', 'failed',
        name='import_job_status',
    )
    import_status.create(op.get_bind(), checkfirst=True)

    # Context export jobs
    op.create_table(
        'context_export_jobs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('org_id', UUID(as_uuid=True), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('status', export_status, nullable=False, server_default='pending'),
        sa.Column('options', JSONB, nullable=False, server_default='{}'),
        sa.Column('file_path', sa.Text, nullable=True),
        sa.Column('file_size', sa.BigInteger, nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_export_jobs_user', 'context_export_jobs', ['org_id', 'user_id'])
    op.create_index('ix_export_jobs_status', 'context_export_jobs', ['status'])

    # Context import jobs
    op.create_table(
        'context_import_jobs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('org_id', UUID(as_uuid=True), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('status', import_status, nullable=False, server_default='pending'),
        sa.Column('options', JSONB, nullable=False, server_default='{}'),
        sa.Column('file_path', sa.Text, nullable=True),
        sa.Column('stats', JSONB, nullable=False, server_default='{}'),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_import_jobs_user', 'context_import_jobs', ['org_id', 'user_id'])
    op.create_index('ix_import_jobs_status', 'context_import_jobs', ['status'])


def downgrade() -> None:
    op.drop_table('context_import_jobs')
    op.drop_table('context_export_jobs')

    sa.Enum(name='import_job_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='export_job_status').drop(op.get_bind(), checkfirst=True)
