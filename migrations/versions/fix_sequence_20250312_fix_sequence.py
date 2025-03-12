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
    # PostgreSQL-specific command to reset the sequence
    # This will set the sequence to start after the maximum existing ID
    op.execute("""
    SELECT setval('stories_id_seq', (SELECT MAX(id) FROM stories), true);
    """)


def downgrade():
    # No downgrade path needed for sequence reset
    pass