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
    # Idempotent: skip if column already exists (re-run after down_revision fix)
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {c['name'] for c in inspector.get_columns('stories')}
    if 'position' not in existing_columns:
        op.add_column('stories', sa.Column('position', sa.Integer(), nullable=True))
        # Default: position = id (preserves existing order)
        op.execute("UPDATE stories SET position = id")
        op.alter_column('stories', 'position', nullable=False, server_default=sa.text('9999'))


def downgrade():
    op.drop_column('stories', 'position')
