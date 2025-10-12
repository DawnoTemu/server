"""Ensure voice allocation columns and events table exist

Revision ID: ffa1b23c67d1
Revises: f1a2c3d4e5b6
Create Date: 2025-05-07 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'ffa1b23c67d1'
down_revision = 'f1a2c3d4e5b6'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    voice_columns = {col['name'] for col in inspector.get_columns('voices')}

    new_columns = [
        ('recording_s3_key', sa.String(length=512)),
        ('recording_filesize', sa.BigInteger()),
        ('allocation_status', sa.String(length=50)),
        ('service_provider', sa.String(length=50)),
        ('elevenlabs_allocated_at', sa.DateTime()),
        ('last_used_at', sa.DateTime()),
        ('slot_lock_expires_at', sa.DateTime()),
    ]

    with op.batch_alter_table('voices') as batch_op:
        for name, column_type in new_columns:
            if name not in voice_columns:
                nullable = name not in ('allocation_status', 'service_provider')
                server_default = None
                if name == 'allocation_status':
                    server_default = 'recorded'
                elif name == 'service_provider':
                    server_default = 'elevenlabs'
                batch_op.add_column(sa.Column(name, column_type, nullable=nullable, server_default=server_default))
                if server_default is not None:
                    batch_op.alter_column(name, server_default=None)

        if 'voices_elevenlabs_voice_id_key' in {idx['name'] for idx in inspector.get_indexes('voices')}:
            try:
                batch_op.drop_constraint('voices_elevenlabs_voice_id_key', type_='unique')
            except Exception:
                pass

    indexes = {idx['name'] for idx in inspector.get_indexes('voices')}
    if 'ix_voices_elevenlabs_voice_id_populated' not in indexes:
        op.create_index(
            'ix_voices_elevenlabs_voice_id_populated',
            'voices',
            ['elevenlabs_voice_id'],
            unique=True,
            postgresql_where=sa.text("elevenlabs_voice_id IS NOT NULL AND elevenlabs_voice_id <> ''"),
            sqlite_where=sa.text("elevenlabs_voice_id IS NOT NULL AND elevenlabs_voice_id <> ''"),
        )

    if 'voice_slot_events' not in inspector.get_table_names():
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
        op.create_index('ix_voice_slot_events_voice_id', 'voice_slot_events', ['voice_id'])
        op.create_index('ix_voice_slot_events_user_id', 'voice_slot_events', ['user_id'])


def downgrade():
    op.drop_index('ix_voice_slot_events_user_id', table_name='voice_slot_events')
    op.drop_index('ix_voice_slot_events_voice_id', table_name='voice_slot_events')
    op.drop_table('voice_slot_events')

    op.drop_index('ix_voices_elevenlabs_voice_id_populated', table_name='voices')

    with op.batch_alter_table('voices') as batch_op:
        for name in [
            'slot_lock_expires_at',
            'last_used_at',
            'elevenlabs_allocated_at',
            'service_provider',
            'allocation_status',
            'recording_filesize',
            'recording_s3_key',
        ]:
            try:
                batch_op.drop_column(name)
            except Exception:
                pass

        batch_op.create_unique_constraint('voices_elevenlabs_voice_id_key', ['elevenlabs_voice_id'])
