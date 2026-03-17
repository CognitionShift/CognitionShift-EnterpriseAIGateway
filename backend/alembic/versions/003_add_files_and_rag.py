"""Add files, chunks, knowledge bases, and embedding support

Revision ID: 003
Revises: 002
Create Date: 2026-03-17
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Files table (enums auto-created by first sa.Enum reference)
    op.create_table('files',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_id', UUID(as_uuid=True), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('mime_type', sa.String(100), nullable=False),
        sa.Column('size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('sha256_hash', sa.String(64), nullable=True),
        sa.Column('storage_path', sa.Text(), nullable=False),
        sa.Column('status', sa.Enum('uploading', 'processing', 'ready', 'failed', 'deleted', name='file_status'), nullable=False, server_default='uploading'),
        sa.Column('access', sa.Enum('private', 'team', 'department', 'org', name='file_access'), nullable=False, server_default='private'),
        sa.Column('team_id', UUID(as_uuid=True), nullable=True),
        sa.Column('metadata', JSONB(), nullable=False, server_default='{}'),
        sa.Column('chunk_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('idx_files_user', 'files', ['user_id', 'created_at'])
    op.create_index('idx_files_org', 'files', ['org_id', 'status'])

    # File chunks table
    op.create_table('file_chunks',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('file_id', UUID(as_uuid=True), sa.ForeignKey('files.id', ondelete='CASCADE'), nullable=False),
        sa.Column('org_id', UUID(as_uuid=True), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('metadata', JSONB(), nullable=False, server_default='{}'),
        sa.Column('token_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_chunks_file', 'file_chunks', ['file_id', 'chunk_index'])
    
    # Add embedding column with pgvector (raw SQL since Alembic doesn't know vector type)
    op.execute("ALTER TABLE file_chunks ADD COLUMN embedding vector(1536)")

    # Knowledge bases table
    op.create_table('knowledge_bases',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_id', UUID(as_uuid=True), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('access', sa.Enum('private', 'team', 'department', 'org', name='file_access', create_type=False), nullable=False, server_default='org'),
        sa.Column('embedding_model', sa.Text(), nullable=False, server_default="'text-embedding-3-small'"),
        sa.Column('settings', JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Knowledge base file association
    op.create_table('knowledge_base_files',
        sa.Column('kb_id', UUID(as_uuid=True), sa.ForeignKey('knowledge_bases.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('file_id', UUID(as_uuid=True), sa.ForeignKey('files.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('added_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )


def downgrade() -> None:
    op.drop_table('knowledge_base_files')
    op.drop_table('knowledge_bases')
    op.drop_table('file_chunks')
    op.drop_table('files')
    op.execute("DROP TYPE IF EXISTS file_status")
    op.execute("DROP TYPE IF EXISTS file_access")
