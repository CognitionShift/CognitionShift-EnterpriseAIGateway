"""Add agent templates and executions

Revision ID: 004
Revises: 003
Create Date: 2026-03-17
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Agent templates
    op.create_table('agent_templates',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_id', UUID(as_uuid=True), sa.ForeignKey('organizations.id'), nullable=True),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('slug', sa.String(100), nullable=False, unique=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(50), nullable=False, server_default='general'),
        sa.Column('system_prompt', sa.Text(), nullable=False),
        sa.Column('tools', JSONB(), nullable=False, server_default='[]'),
        sa.Column('constraints', JSONB(), nullable=False, server_default='{}'),
        sa.Column('default_model', sa.Text(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_system', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_by', UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )

    # Agent executions
    op.create_table('agent_executions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_id', UUID(as_uuid=True), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('template_id', UUID(as_uuid=True), sa.ForeignKey('agent_templates.id'), nullable=False),
        sa.Column('conversation_id', UUID(as_uuid=True), sa.ForeignKey('conversations.id'), nullable=True),
        sa.Column('status', sa.Enum('pending', 'running', 'completed', 'failed', 'cancelled', 'timeout', name='agent_status'), nullable=False, server_default='pending'),
        sa.Column('input_data', JSONB(), nullable=False, server_default='{}'),
        sa.Column('output_data', JSONB(), nullable=True),
        sa.Column('model_id', sa.Text(), nullable=True),
        sa.Column('steps', JSONB(), nullable=False, server_default='[]'),
        sa.Column('total_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_cost_usd', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('idx_agent_exec_user', 'agent_executions', ['user_id', 'created_at'])
    op.create_index('idx_agent_exec_status', 'agent_executions', ['status'])

    # Seed system agent templates
    op.execute("""
        INSERT INTO agent_templates (name, slug, description, category, system_prompt, tools, constraints, is_system, default_model) VALUES
        ('Research Assistant', 'research-assistant', 'Searches and synthesizes information on a topic. Provides cited summaries.', 'research',
         'You are a research assistant. When given a topic, provide a comprehensive, well-structured analysis. Include key findings, cite your reasoning, and present multiple perspectives. Be thorough but concise.',
         '[]', '{"max_tokens": 8192, "max_steps": 5}', true, 'claude-sonnet-4-20250514'),
        ('Writing Assistant', 'writing-assistant', 'Helps improve and refine written content. Checks style, grammar, and clarity.', 'writing',
         'You are a professional writing assistant. Analyze the provided text and suggest improvements for clarity, style, grammar, and structure. Be specific with suggestions and explain your reasoning.',
         '[]', '{"max_tokens": 8192, "max_steps": 3}', true, 'claude-sonnet-4-20250514'),
        ('Code Review', 'code-review', 'Reviews code for bugs, security issues, and best practices.', 'development',
         'You are a senior code reviewer. Analyze the provided code for: 1) Bugs and logic errors, 2) Security vulnerabilities, 3) Performance issues, 4) Code style and best practices. Provide specific, actionable feedback with code examples where helpful.',
         '[]', '{"max_tokens": 8192, "max_steps": 3}', true, 'claude-sonnet-4-20250514'),
        ('Document Analyzer', 'document-analyzer', 'Analyzes documents for key information, inconsistencies, and insights.', 'analysis',
         'You are a document analysis expert. Analyze the provided document and extract: 1) Key findings and main points, 2) Any inconsistencies or gaps, 3) Actionable insights, 4) Summary recommendations. Be thorough and precise.',
         '[]', '{"max_tokens": 8192, "max_steps": 5}', true, 'claude-sonnet-4-20250514'),
        ('Summarizer', 'summarizer', 'Creates concise summaries of long content.', 'general',
         'You are an expert summarizer. Create a clear, concise summary of the provided content. Capture the most important points, maintain accuracy, and organize information logically. Provide both a brief (1-2 sentence) and detailed summary.',
         '[]', '{"max_tokens": 4096, "max_steps": 2}', true, 'claude-3-5-haiku-20241022')
    """)


def downgrade() -> None:
    op.drop_table('agent_executions')
    op.drop_table('agent_templates')
    op.execute("DROP TYPE IF EXISTS agent_status")
