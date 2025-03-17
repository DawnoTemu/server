"""Create stories table

Revision ID: 96fdb828fe76
Revises: 
Create Date: 2025-03-10 23:16:30.995696

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime


# revision identifiers, used by Alembic.
revision = '96fdb828fe76'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # First create the stories table with all required columns
    op.create_table('stories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('author', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('cover_filename', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True, default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime(), nullable=True, default=datetime.utcnow, onupdate=datetime.utcnow),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Then add the s3_cover_key column (though this could be included in the create_table above)
    op.add_column('stories', sa.Column('s3_cover_key', sa.String(512), nullable=True))


def downgrade():
    # Remove s3_cover_key column from stories table
    op.drop_column('stories', 's3_cover_key')
    
    # Drop the stories table
    op.drop_table('stories')