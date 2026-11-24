"""add_document_source_fields

Revision ID: 7a3d9e1f5b2c
Revises: 64ca298e56fd
Create Date: 2026-11-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7a3d9e1f5b2c'
down_revision: Union[str, None] = '64ca298e56fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add nullable source_url and source_title to documents table
    op.add_column('documents', sa.Column('source_url', sa.String(length=2048), nullable=True))
    op.add_column('documents', sa.Column('source_title', sa.String(length=512), nullable=True))
    # file_type is already VARCHAR(8) without enum/check constraints, which allows 'html' (length 4).


def downgrade() -> None:
    op.drop_column('documents', 'source_title')
    op.drop_column('documents', 'source_url')
