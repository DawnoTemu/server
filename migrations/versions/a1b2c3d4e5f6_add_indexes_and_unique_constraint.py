"""add indexes and unique constraint for load testing

Revision ID: a1b2c3d4e5f6
Revises: 7e9ed0702b83
Create Date: 2026-03-03

Adds:
- Unique constraint on audio_stories(story_id, voice_id) to prevent TOCTOU race
- Index on voices(allocation_status) for slot capacity queries
- Composite index on credit_transactions(audio_story_id, type, status) for debit lookups
"""
from alembic import op


revision = 'a1b2c3d4e5f6'
down_revision = '7e9ed0702b83'
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint(
        'uq_audio_stories_story_voice',
        'audio_stories',
        ['story_id', 'voice_id'],
    )

    op.create_index(
        'ix_voices_allocation_status',
        'voices',
        ['allocation_status'],
    )

    op.create_index(
        'ix_credit_tx_audio_type_status',
        'credit_transactions',
        ['audio_story_id', 'type', 'status'],
    )


def downgrade():
    op.drop_index('ix_credit_tx_audio_type_status', table_name='credit_transactions')
    op.drop_index('ix_voices_allocation_status', table_name='voices')
    op.drop_unique_constraint('uq_audio_stories_story_voice', table_name='audio_stories')
