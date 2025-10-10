"""add credits_balance to users

Revision ID: 7f3e9c2a1b5d
Revises: 63206a3545a2
Create Date: 2025-03-24 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7f3e9c2a1b5d'
down_revision = '63206a3545a2'
branch_labels = None
depends_on = None


def upgrade():
    # Add column with server_default to backfill existing rows, then keep default
    op.add_column('users', sa.Column('credits_balance', sa.Integer(), server_default='0', nullable=False))


def downgrade():
    op.drop_column('users', 'credits_balance')

