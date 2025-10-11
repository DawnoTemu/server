"""Voice metadata and slot events

Revision ID: f1a2c3d4e5b6
Revises: e0e59f1eaa8e
Create Date: 2025-05-06 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = 'f1a2c3d4e5b6'
down_revision = 'e5b7c9d1aa00'
branch_labels = None
depends_on = None


def upgrade():
    # Extend voices table with allocation metadata
    with op.batch_alter_table('voices', schema=None) as batch_op:
        batch_op.add_column(sa.Column('recording_s3_key', sa.String(length=512), nullable=True))
        batch_op.add_column(sa.Column('recording_filesize', sa.BigInteger(), nullable=True))
        batch_op.add_column(sa.Column('allocation_status', sa.String(length=50), nullable=False, server_default='recorded'))
        batch_op.add_column(sa.Column('service_provider', sa.String(length=50), nullable=False, server_default='elevenlabs'))
        batch_op.add_column(sa.Column('elevenlabs_allocated_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('last_used_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('slot_lock_expires_at', sa.DateTime(), nullable=True))

        # Drop existing unique constraint on elevenlabs_voice_id if present
        try:
            batch_op.drop_constraint('voices_elevenlabs_voice_id_key', type_='unique')
        except Exception:
            # Constraint might already be absent in some environments
            pass

    # Ensure allocation metadata is populated for existing voices
    conn = op.get_bind()
    conn.execute(
        text(
            """
            UPDATE voices
            SET allocation_status = 'ready',
                service_provider = COALESCE(NULLIF(service_provider, ''), 'elevenlabs'),
                elevenlabs_allocated_at = COALESCE(elevenlabs_allocated_at, updated_at, created_at),
                last_used_at = COALESCE(last_used_at, updated_at, created_at)
            WHERE elevenlabs_voice_id IS NOT NULL AND elevenlabs_voice_id <> ''
            """
        )
    )

    # Create partial unique index that only applies when an ElevenLabs ID is populated
    op.create_index(
        'ix_voices_elevenlabs_voice_id_populated',
        'voices',
        ['elevenlabs_voice_id'],
        unique=True,
        postgresql_where=text("elevenlabs_voice_id IS NOT NULL AND elevenlabs_voice_id <> ''"),
        sqlite_where=text("elevenlabs_voice_id IS NOT NULL AND elevenlabs_voice_id <> ''")
    )

    # Create voice_slot_events table for allocation auditing
    op.create_table(
        'voice_slot_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('voice_id', sa.Integer(), sa.ForeignKey('voices.id', ondelete='SET NULL'), nullable=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('reason', sa.String(length=255), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_voice_slot_events_voice_id', 'voice_slot_events', ['voice_id'], unique=False)
    op.create_index('ix_voice_slot_events_user_id', 'voice_slot_events', ['user_id'], unique=False)


def downgrade():
    # Drop voice_slot_events table and indexes
    op.drop_index('ix_voice_slot_events_user_id', table_name='voice_slot_events')
    op.drop_index('ix_voice_slot_events_voice_id', table_name='voice_slot_events')
    op.drop_table('voice_slot_events')

    # Remove partial unique index
    op.drop_index('ix_voices_elevenlabs_voice_id_populated', table_name='voices')

    # Remove added columns and restore previous unique constraint
    with op.batch_alter_table('voices', schema=None) as batch_op:
        batch_op.drop_column('slot_lock_expires_at')
        batch_op.drop_column('last_used_at')
        batch_op.drop_column('elevenlabs_allocated_at')
        batch_op.drop_column('service_provider')
        batch_op.drop_column('allocation_status')
        batch_op.drop_column('recording_filesize')
        batch_op.drop_column('recording_s3_key')

        batch_op.create_unique_constraint('voices_elevenlabs_voice_id_key', ['elevenlabs_voice_id'])
