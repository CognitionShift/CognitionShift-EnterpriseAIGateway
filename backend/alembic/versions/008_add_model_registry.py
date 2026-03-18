"""Add model registry tables

Revision ID: 008
Revises: 007
Create Date: 2026-03-17
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = '008'
down_revision: Union[str, None] = '007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Model registry
    op.create_table('model_registry',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_id', UUID(as_uuid=True), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('display_name', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('visibility', sa.Enum('private', 'department', 'organization', name='model_visibility'), nullable=False, server_default='private'),
        sa.Column('department_id', UUID(as_uuid=True), sa.ForeignKey('departments.id'), nullable=True),
        sa.Column('tags', JSONB(), nullable=False, server_default='[]'),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('org_id', 'name', name='uq_model_registry_org_name'),
    )
    op.create_index('ix_model_registry_org_id', 'model_registry', ['org_id'])
    op.create_index('ix_model_registry_created_by', 'model_registry', ['created_by'])
    op.create_index('ix_model_registry_visibility', 'model_registry', ['visibility'])

    # Model versions
    op.create_table('model_versions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('model_id', UUID(as_uuid=True), sa.ForeignKey('model_registry.id', ondelete='CASCADE'), nullable=False),
        sa.Column('version', sa.String(50), nullable=False),
        sa.Column('status', sa.Enum('draft', 'published', 'deprecated', name='version_status'), nullable=False, server_default='draft'),
        sa.Column('release_notes', sa.Text(), nullable=True),
        sa.Column('training_data', JSONB(), nullable=True),
        sa.Column('intended_use', sa.Text(), nullable=True),
        sa.Column('limitations', sa.Text(), nullable=True),
        sa.Column('license', sa.String(100), nullable=True),
        sa.Column('architecture', JSONB(), nullable=True),
        sa.Column('eval_results', JSONB(), nullable=True),
        sa.Column('artifact_uri', sa.Text(), nullable=True),
        sa.Column('artifact_size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('artifact_hash', sa.String(128), nullable=True),
        sa.Column('gateway_config', JSONB(), nullable=True),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.UniqueConstraint('model_id', 'version', name='uq_model_versions_model_version'),
    )
    op.create_index('ix_model_versions_model_id', 'model_versions', ['model_id'])
    op.create_index('ix_model_versions_status', 'model_versions', ['status'])

    # Model access grants
    op.create_table('model_access',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('model_id', UUID(as_uuid=True), sa.ForeignKey('model_registry.id', ondelete='CASCADE'), nullable=False),
        sa.Column('grantee_type', sa.Enum('user', 'department', 'organization', name='access_grantee_type'), nullable=False),
        sa.Column('grantee_id', UUID(as_uuid=True), nullable=False),
        sa.Column('permission', sa.Enum('view', 'use', 'edit', 'admin', name='access_permission'), nullable=False),
        sa.Column('granted_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_model_access_model_id', 'model_access', ['model_id'])
    op.create_index('ix_model_access_grantee', 'model_access', ['grantee_type', 'grantee_id'])


def downgrade() -> None:
    op.drop_table('model_access')
    op.drop_table('model_versions')
    op.drop_table('model_registry')
    op.execute('DROP TYPE IF EXISTS access_permission')
    op.execute('DROP TYPE IF EXISTS access_grantee_type')
    op.execute('DROP TYPE IF EXISTS version_status')
    op.execute('DROP TYPE IF EXISTS model_visibility')
