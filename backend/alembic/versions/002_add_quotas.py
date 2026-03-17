"""Add quotas table

Revision ID: 002
Revises: 001
Create Date: 2026-03-17
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('quotas',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_id', UUID(as_uuid=True), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('scope', sa.String(20), nullable=False, server_default='org'),
        sa.Column('scope_id', UUID(as_uuid=True), nullable=True),
        sa.Column('period', sa.String(20), nullable=False, server_default='monthly'),
        sa.Column('max_tokens', sa.Integer(), nullable=True),
        sa.Column('max_cost_usd', sa.Numeric(10, 2), nullable=True),
        sa.Column('max_requests', sa.Integer(), nullable=True),
        sa.Column('enforcement', sa.String(20), nullable=False, server_default='soft'),
        sa.Column('active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_quotas_org', 'quotas', ['org_id', 'scope'])


def downgrade() -> None:
    op.drop_table('quotas')
