"""add credit tables and audio credits_charged

Revision ID: 9c1f2d3e4a56
Revises: 7f3e9c2a1b5d
Create Date: 2025-03-24 12:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9c1f2d3e4a56'
down_revision = '7f3e9c2a1b5d'
branch_labels = None
depends_on = None


def upgrade():
    # 1) Add credits_charged to audio_stories
    op.add_column('audio_stories', sa.Column('credits_charged', sa.Integer(), nullable=True))

    # 2) credit_transactions ledger
    op.create_table(
        'credit_transactions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),  # debit | credit | refund | expire
        sa.Column('reason', sa.String(length=255), nullable=True),
        sa.Column('audio_story_id', sa.Integer(), sa.ForeignKey('audio_stories.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('story_id', sa.Integer(), sa.ForeignKey('stories.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='applied'),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # Unique protection against duplicate open (status='applied') debit per (audio_story, user)
    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else None
    if dialect in ('postgresql', 'sqlite'):
        op.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_credit_tx_open_debit
            ON credit_transactions (audio_story_id, user_id)
            WHERE type = 'debit' AND status = 'applied'
        """)
    else:
        # Other dialects without partial indexes: skip uniqueness here and
        # enforce at application level to avoid blocking non-debit transactions.
        pass

    # 3) credit_lots to support sources and expirations
    op.create_table(
        'credit_lots',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('source', sa.String(length=20), nullable=False),  # monthly | add_on | free | event | referral
        sa.Column('amount_granted', sa.Integer(), nullable=False),
        sa.Column('amount_remaining', sa.Integer(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # Index to accelerate expiration queries and per-user listing
    op.create_index('ix_credit_lots_user_expires', 'credit_lots', ['user_id', 'expires_at'])

    # 4) transaction allocations across lots (many-to-many with amounts)
    op.create_table(
        'credit_transaction_allocations',
        sa.Column('transaction_id', sa.Integer(), sa.ForeignKey('credit_transactions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('lot_id', sa.Integer(), sa.ForeignKey('credit_lots.id', ondelete='CASCADE'), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),  # signed; negative for refunds back to a lot
        sa.PrimaryKeyConstraint('transaction_id', 'lot_id', name='pk_credit_tx_allocations')
    )


def downgrade():
    # Drop allocation table first due to FK dependencies
    op.drop_table('credit_transaction_allocations')
    # Drop index and lots
    op.drop_index('ix_credit_lots_user_expires', table_name='credit_lots')
    op.drop_table('credit_lots')

    # Drop unique constraint or partial index depending on dialect
    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else None
    if dialect in ('postgresql', 'sqlite'):
        op.execute("DROP INDEX IF EXISTS uq_credit_tx_open_debit")
    else:
        # No index/constraint was created for other dialects in upgrade()
        pass
    op.drop_table('credit_transactions')

    # Finally drop audio_stories column
    op.drop_column('audio_stories', 'credits_charged')
