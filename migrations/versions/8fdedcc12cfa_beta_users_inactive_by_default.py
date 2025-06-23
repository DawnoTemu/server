"""beta_users_inactive_by_default

Revision ID: 8fdedcc12cfa
Revises: e0e59f1eaa8e
Create Date: 2025-06-23 13:11:38.593134

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8fdedcc12cfa'
down_revision = 'e0e59f1eaa8e'
branch_labels = None
depends_on = None


def upgrade():
    # Set all existing users to inactive for beta phase
    op.execute("UPDATE users SET is_active = false")


def downgrade():
    # Revert all users back to active (if needed)
    op.execute("UPDATE users SET is_active = true")
