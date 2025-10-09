"""fix_sequence

Revision ID: fix_sequence_20250312
Revises: a36a09dda7c8
Create Date: 2025-03-12 10:42:58.896806

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fix_sequence_20250312'
down_revision = 'a36a09dda7c8'
branch_labels = None
depends_on = None


def upgrade():
    # Run only on PostgreSQL; no-op elsewhere (e.g., SQLite in dev/test)
    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else None
    if dialect == 'postgresql':
        op.execute(
            """
            SELECT setval('stories_id_seq', (SELECT MAX(id) FROM stories), true);
            """
        )


def downgrade():
    # No downgrade path needed for sequence reset
    pass
