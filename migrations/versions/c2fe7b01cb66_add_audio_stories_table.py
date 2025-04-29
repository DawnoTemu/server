"""Add audio_stories table

Revision ID: c2fe7b01cb66
Revises: 4bd560177d15
Create Date: 2025-04-29 11:24:48.439655

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime


# revision identifiers, used by Alembic.
revision = 'c2fe7b01cb66'
down_revision = '4bd560177d15'
branch_labels = None
depends_on = None


def upgrade():
    """Add the audio_stories table"""
    op.create_table('audio_stories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('story_id', sa.Integer(), nullable=False),
        sa.Column('voice_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('elevenlabs_voice_id', sa.String(255), nullable=True),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('s3_key', sa.String(512), nullable=True),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('file_size_bytes', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True, default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime(), nullable=True, default=datetime.utcnow, onupdate=datetime.utcnow),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['story_id'], ['stories.id'], ),
        sa.ForeignKeyConstraint(['voice_id'], ['voices.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], )
    )
    
    # Add indexes for faster lookup
    op.create_index('ix_audio_stories_story_id', 'audio_stories', ['story_id'], unique=False)
    op.create_index('ix_audio_stories_voice_id', 'audio_stories', ['voice_id'], unique=False)
    op.create_index('ix_audio_stories_user_id', 'audio_stories', ['user_id'], unique=False)
    op.create_index('ix_audio_stories_elevenlabs_voice_id', 'audio_stories', ['elevenlabs_voice_id'], unique=False)
    op.create_index('ix_audio_stories_status', 'audio_stories', ['status'], unique=False)
    
    # Create a unique constraint to ensure only one audio per story/voice combination
    op.create_index('ix_audio_stories_story_voice', 'audio_stories', ['story_id', 'voice_id'], unique=True)


def downgrade():
    """Remove the audio_stories table"""
    # Drop indexes first
    op.drop_index('ix_audio_stories_story_voice', table_name='audio_stories')
    op.drop_index('ix_audio_stories_status', table_name='audio_stories')
    op.drop_index('ix_audio_stories_elevenlabs_voice_id', table_name='audio_stories')
    op.drop_index('ix_audio_stories_user_id', table_name='audio_stories')
    op.drop_index('ix_audio_stories_voice_id', table_name='audio_stories')
    op.drop_index('ix_audio_stories_story_id', table_name='audio_stories')
    
    # Drop the table
    op.drop_table('audio_stories')
