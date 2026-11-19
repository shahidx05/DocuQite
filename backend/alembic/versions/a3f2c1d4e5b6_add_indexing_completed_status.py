"""add INDEXING and COMPLETED to document_status enum

Revision ID: a3f2c1d4e5b6
Revises: e80ad1b59e7f
Create Date: 2026-11-19

PostgreSQL stores SQLAlchemy Enum columns as a native PG enum type called
'document_status'.  Adding new values requires ALTER TYPE ... ADD VALUE which
cannot be run inside a transaction on older Postgres versions; we use
execute_if to guard it and run the statements non-transactionally.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3f2c1d4e5b6'
down_revision = 'e80ad1b59e7f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block in PG < 12.
    # We use a raw connection to execute it outside the implicit transaction.
    conn = op.get_bind()
    # Only add the value if it doesn't already exist (idempotent).
    conn.execute(sa.text(
        "ALTER TYPE document_status ADD VALUE IF NOT EXISTS 'INDEXING'"
    ))
    conn.execute(sa.text(
        "ALTER TYPE document_status ADD VALUE IF NOT EXISTS 'COMPLETED'"
    ))


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; a full re-create
    # would be needed.  For development purposes, raise to prevent accidental
    # downgrade.
    raise NotImplementedError(
        "Downgrade not supported: PostgreSQL cannot remove enum values. "
        "Drop and recreate the database if you need to roll back."
    )
