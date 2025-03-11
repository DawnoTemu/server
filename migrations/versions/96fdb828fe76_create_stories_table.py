"""Create stories table

Revision ID: 96fdb828fe76
Revises: 
Create Date: 2025-03-10 23:16:30.995696

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '96fdb828fe76'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Add s3_cover_key column to stories table
    op.add_column('stories', sa.Column('s3_cover_key', sa.String(512), nullable=True))


def downgrade():
    # Remove s3_cover_key column from stories table
    op.drop_column('stories', 's3_cover_key')