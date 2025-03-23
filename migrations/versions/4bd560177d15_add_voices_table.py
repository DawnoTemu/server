"""Add voices table

Revision ID: 4bd560177d15
Revises: 54e95d96a3e3
Create Date: 2025-03-23 22:22:56.094579

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime


# revision identifiers, used by Alembic.
revision = '4bd560177d15'
down_revision = '54e95d96a3e3'
branch_labels = None
depends_on = None


def upgrade():
    # Create voices table
    op.create_table('voices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('elevenlabs_voice_id', sa.String(255), nullable=False),
        sa.Column('s3_sample_key', sa.String(512), nullable=True),
        sa.Column('sample_filename', sa.String(255), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('elevenlabs_voice_id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], )
    )
    
    # Add index on user_id for faster queries
    op.create_index('ix_voices_user_id', 'voices', ['user_id'], unique=False)



def downgrade():
    # Drop index
    op.drop_index('ix_voices_user_id', table_name='voices')

    # Drop voices table
    op.drop_table('voices')
