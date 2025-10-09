"""backfill free lots for existing users

Revision ID: e5b7c9d1aa00
Revises: d3f4e5a6b7c8
Create Date: 2025-03-24 14:05:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'e5b7c9d1aa00'
down_revision = 'd3f4e5a6b7c8'
branch_labels = None
depends_on = None


def upgrade():
    # Seed a non-expiring 'free' credit lot of 10 points for users with no lots
    # and bump cached credits_balance accordingly.
    # This prevents immediate 402s for existing users after enabling charging.
    op.execute(
        """
        INSERT INTO credit_lots (user_id, source, amount_granted, amount_remaining, expires_at, created_at, updated_at)
        SELECT u.id, 'free', 10, 10, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM users u
        LEFT JOIN credit_lots cl ON cl.user_id = u.id
        WHERE cl.user_id IS NULL
        """
    )

    # Update cached balances for those users we just seeded
    op.execute(
        """
        UPDATE users AS u
        SET credits_balance = COALESCE(credits_balance, 0) + 10
        WHERE NOT EXISTS (
            SELECT 1 FROM credit_lots cl WHERE cl.user_id = u.id AND cl.amount_granted > 0 AND cl.source = 'free' AND cl.created_at >= CURRENT_DATE
        ) IS FALSE
        """
    )


def downgrade():
    # Best-effort rollback: remove only lots created by this migration today with amount 10 and source 'free'
    op.execute(
        """
        DELETE FROM credit_lots
        WHERE source = 'free' AND amount_granted = 10 AND DATE(created_at) = CURRENT_DATE
        """
    )
    # Cannot reliably decrement credits_balance on downgrade due to unknown concurrent mutations
    # so we leave balances as-is.

