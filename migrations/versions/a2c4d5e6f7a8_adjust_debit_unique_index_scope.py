"""adjust debit unique index scope to include user_id

Revision ID: a2c4d5e6f7a8
Revises: 9c1f2d3e4a56
Create Date: 2025-03-24 13:05:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'a2c4d5e6f7a8'
down_revision = '9c1f2d3e4a56'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else None
    if dialect in ('postgresql', 'sqlite'):
        # Replace prior partial unique index with one scoped to (audio_story_id, user_id)
        op.execute("DROP INDEX IF EXISTS uq_credit_tx_debit_per_audio")
        op.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_credit_tx_debit_per_audio_user
            ON credit_transactions (audio_story_id, user_id)
            WHERE type = 'debit'
            """
        )
    else:
        # No-op for other dialects (app-level enforcement)
        pass


def downgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else None
    if dialect in ('postgresql', 'sqlite'):
        op.execute("DROP INDEX IF EXISTS uq_credit_tx_debit_per_audio_user")
        op.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_credit_tx_debit_per_audio
            ON credit_transactions (audio_story_id)
            WHERE type = 'debit'
            """
        )
    else:
        # No-op
        pass

