"""backfill free lots for existing users

Revision ID: e5b7c9d1aa00
Revises: d3f4e5a6b7c8
Create Date: 2025-03-24 14:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5b7c9d1aa00'
down_revision = 'd3f4e5a6b7c8'
branch_labels = None
depends_on = None


def upgrade():
    """Seed non-expiring 'free' credit lots for existing users without any lots,
    and bump cached balances ONLY for those users. Uses Python to compute the
    eligible set to avoid double-counting when the app already created lots.
    """
    bind = op.get_bind()
    # 1) Find users with no credit lots at all
    eligible = [
        row[0]
        for row in bind.execute(sa.text(
            """
            SELECT u.id
            FROM users u
            WHERE NOT EXISTS (
                SELECT 1 FROM credit_lots cl WHERE cl.user_id = u.id
            )
            """
        )).fetchall()
    ]

    if not eligible:
        return

    # 2) Insert a free lot for each eligible user
    insert_stmt = sa.text(
        """
        INSERT INTO credit_lots (user_id, source, amount_granted, amount_remaining, expires_at, created_at, updated_at)
        VALUES (:uid, 'free', 10, 10, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
    )
    update_stmt = sa.text(
        """
        UPDATE users SET credits_balance = COALESCE(credits_balance, 0) + 10
        WHERE id = :uid
        """
    )
    for uid in eligible:
        bind.execute(insert_stmt, {"uid": uid})
        bind.execute(update_stmt, {"uid": uid})


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
