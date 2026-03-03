"""add story position

Revision ID: 3405be6b412c
Revises: fix_sequence_20250312
Create Date: 2026-03-02

"""
from alembic import op
import sqlalchemy as sa

revision = '3405be6b412c'
down_revision = 'fix_sequence_20250312'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('stories', sa.Column('position', sa.Integer(), nullable=True))
    # Default: position = id (preserves existing order)
    op.execute("UPDATE stories SET position = id")
    op.alter_column('stories', 'position', nullable=False, server_default=sa.text('9999'))


def downgrade():
    op.drop_column('stories', 'position')
