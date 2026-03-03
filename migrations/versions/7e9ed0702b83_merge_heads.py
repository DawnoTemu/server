"""merge heads

Revision ID: 7e9ed0702b83
Revises: 3405be6b412c, ffa1b23c67d1
Create Date: 2026-03-03 15:17:36.210073

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7e9ed0702b83'
down_revision = ('3405be6b412c', 'ffa1b23c67d1')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
