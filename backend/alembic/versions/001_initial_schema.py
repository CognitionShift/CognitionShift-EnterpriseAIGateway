"""Initial schema - organizations, users, conversations, messages, api_keys, audit, usage

Revision ID: 001
Revises: 
Create Date: 2026-03-16
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET, ARRAY

revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Note: enums are auto-created by the first sa.Enum column that references them

    # Organizations
    op.create_table('organizations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('slug', sa.String(100), nullable=False, unique=True),
        sa.Column('settings', JSONB(), nullable=False, server_default='{}'),
        sa.Column('content_policy', JSONB(), nullable=False, server_default='{}'),
        sa.Column('retention_policy', JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Divisions
    op.create_table('divisions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_id', UUID(as_uuid=True), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('slug', sa.String(100), nullable=False),
        sa.Column('settings', JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('org_id', 'slug'),
    )

    # Departments
    op.create_table('departments',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_id', UUID(as_uuid=True), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('division_id', UUID(as_uuid=True), sa.ForeignKey('divisions.id'), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('slug', sa.String(100), nullable=False),
        sa.Column('settings', JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('division_id', 'slug'),
    )

    # Teams
    op.create_table('teams',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_id', UUID(as_uuid=True), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('department_id', UUID(as_uuid=True), sa.ForeignKey('departments.id'), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('slug', sa.String(100), nullable=False),
        sa.Column('settings', JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('department_id', 'slug'),
    )

    # Users
    op.create_table('users',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_id', UUID(as_uuid=True), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('role', sa.Enum('admin', 'manager', 'member', 'viewer', 'pending', name='user_role'), nullable=False, server_default='member'),
        sa.Column('password_hash', sa.Text(), nullable=True),
        sa.Column('avatar_url', sa.Text(), nullable=True),
        sa.Column('settings', JSONB(), nullable=False, server_default='{}'),
        sa.Column('division_id', UUID(as_uuid=True), sa.ForeignKey('divisions.id'), nullable=True),
        sa.Column('department_id', UUID(as_uuid=True), sa.ForeignKey('departments.id'), nullable=True),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('org_id', 'email'),
    )

    # Team memberships
    op.create_table('team_memberships',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('team_id', UUID(as_uuid=True), sa.ForeignKey('teams.id'), nullable=False),
        sa.Column('role', sa.Enum('admin', 'manager', 'member', 'viewer', 'pending', name='user_role', create_type=False), nullable=False, server_default='member'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('user_id', 'team_id'),
    )

    # Conversations
    op.create_table('conversations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_id', UUID(as_uuid=True), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('visibility', sa.Enum('private', 'team', 'department', 'org', name='conversation_visibility'), nullable=False, server_default='private'),
        sa.Column('team_id', UUID(as_uuid=True), sa.ForeignKey('teams.id'), nullable=True),
        sa.Column('model_id', sa.Text(), nullable=True),
        sa.Column('system_prompt', sa.Text(), nullable=True),
        sa.Column('metadata', JSONB(), nullable=False, server_default='{}'),
        sa.Column('is_ephemeral', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('pinned', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('archived', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('idx_conversations_user', 'conversations', ['user_id', 'created_at'], postgresql_where=sa.text('deleted_at IS NULL'))

    # Messages
    op.create_table('messages',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('conversation_id', UUID(as_uuid=True), sa.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('org_id', UUID(as_uuid=True), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('model_id', sa.Text(), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Numeric(10, 6), nullable=True),
        sa.Column('safety_flags', JSONB(), nullable=True),
        sa.Column('metadata', JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('conversation_id', 'sequence'),
        sa.CheckConstraint("role IN ('user', 'assistant', 'system', 'tool')", name='ck_message_role'),
    )
    op.create_index('idx_messages_conversation', 'messages', ['conversation_id', 'sequence'], postgresql_where=sa.text('deleted_at IS NULL'))

    # API Keys
    op.create_table('api_keys',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('org_id', UUID(as_uuid=True), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('key_hash', sa.Text(), nullable=False, unique=True),
        sa.Column('key_prefix', sa.String(12), nullable=False),
        sa.Column('scopes', ARRAY(sa.Text()), nullable=False, server_default='{}'),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Audit Log
    op.create_table('audit_log',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_id', UUID(as_uuid=True), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('actor_id', UUID(as_uuid=True), nullable=True),
        sa.Column('actor_type', sa.String(20), nullable=False),
        sa.Column('actor_ip', INET(), nullable=True),
        sa.Column('action', sa.Text(), nullable=False),
        sa.Column('resource_type', sa.Text(), nullable=False),
        sa.Column('resource_id', UUID(as_uuid=True), nullable=True),
        sa.Column('details', JSONB(), nullable=False, server_default='{}'),
        sa.Column('safety_event', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_audit_log_org_created', 'audit_log', ['org_id', 'created_at'])
    op.create_index('idx_audit_log_actor', 'audit_log', ['actor_id', 'created_at'])

    # Usage Log
    op.create_table('usage_log',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_id', UUID(as_uuid=True), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('conversation_id', UUID(as_uuid=True), sa.ForeignKey('conversations.id'), nullable=True),
        sa.Column('message_id', UUID(as_uuid=True), sa.ForeignKey('messages.id'), nullable=True),
        sa.Column('model_id', sa.Text(), nullable=False),
        sa.Column('provider', sa.Text(), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=False),
        sa.Column('output_tokens', sa.Integer(), nullable=False),
        sa.Column('cost_usd', sa.Numeric(10, 6), nullable=False),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('division_id', UUID(as_uuid=True), nullable=True),
        sa.Column('department_id', UUID(as_uuid=True), nullable=True),
        sa.Column('team_id', UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_usage_log_analytics', 'usage_log', ['org_id', 'created_at'])
    op.create_index('idx_usage_log_user', 'usage_log', ['user_id', 'created_at'])


def downgrade() -> None:
    op.drop_table('usage_log')
    op.drop_table('audit_log')
    op.drop_table('api_keys')
    op.drop_table('messages')
    op.drop_table('conversations')
    op.drop_table('team_memberships')
    op.drop_table('users')
    op.drop_table('teams')
    op.drop_table('departments')
    op.drop_table('divisions')
    op.drop_table('organizations')
    op.execute("DROP TYPE IF EXISTS user_role")
    op.execute("DROP TYPE IF EXISTS conversation_visibility")
