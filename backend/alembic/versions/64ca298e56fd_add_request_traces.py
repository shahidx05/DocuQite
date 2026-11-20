"""add_request_traces

Revision ID: 64ca298e56fd
Revises: e6aefaa488cf
Create Date: 2026-11-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '64ca298e56fd'
down_revision: Union[str, None] = 'e6aefaa488cf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'request_traces',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('workspace_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.Column('provider', sa.String(length=32), nullable=False),
        sa.Column('model', sa.String(length=64), nullable=False),
        sa.Column('question_length', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('rewrite_ms', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('embed_ms', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('qdrant_ms', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('rerank_ms', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('llm_ms', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('total_ms', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('input_tokens', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('output_tokens', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('estimated_cost_usd', sa.Float(), nullable=False, server_default=sa.text('0.0')),
        sa.Column('candidates_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('abstained', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('top_rerank_score', sa.Float(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_request_traces_created_at'), 'request_traces', ['created_at'], unique=False)
    op.create_index(op.f('ix_request_traces_user_id'), 'request_traces', ['user_id'], unique=False)
    op.create_index(op.f('ix_request_traces_workspace_id'), 'request_traces', ['workspace_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_request_traces_workspace_id'), table_name='request_traces')
    op.drop_index(op.f('ix_request_traces_user_id'), table_name='request_traces')
    op.drop_index(op.f('ix_request_traces_created_at'), table_name='request_traces')
    op.drop_table('request_traces')
