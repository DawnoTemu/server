"""open debit index on status=applied

Revision ID: d3f4e5a6b7c8
Revises: a2c4d5e6f7a8
Create Date: 2025-03-24 13:20:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'd3f4e5a6b7c8'
down_revision = 'a2c4d5e6f7a8'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else None
    if dialect in ('postgresql', 'sqlite'):
        op.execute("DROP INDEX IF EXISTS uq_credit_tx_debit_per_audio_user")
        op.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_credit_tx_open_debit
            ON credit_transactions (audio_story_id, user_id)
            WHERE type = 'debit' AND status = 'applied'
            """
        )
    else:
        # No-op for other dialects; enforce via application logic
        pass


def downgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else None
    if dialect in ('postgresql', 'sqlite'):
        op.execute("DROP INDEX IF EXISTS uq_credit_tx_open_debit")
        op.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_credit_tx_debit_per_audio_user
            ON credit_transactions (audio_story_id, user_id)
            WHERE type = 'debit'
            """
        )
    else:
        # No-op
        pass

