"""Add subscription/trial fields to users, consumed_addon_transactions and webhook_events tables

Revision ID: b7e8f9a0c1d2
Revises: a1b2c3d4e5f6
Create Date: 2026-03-22
"""
from alembic import op
import sqlalchemy as sa

revision = 'b7e8f9a0c1d2'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add subscription/trial columns to users
    op.add_column('users', sa.Column('trial_expires_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column(
        'subscription_active', sa.Boolean(), nullable=False, server_default=sa.text('false'),
    ))
    op.add_column('users', sa.Column('subscription_plan', sa.String(50), nullable=True))
    op.add_column('users', sa.Column('subscription_expires_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column(
        'subscription_will_renew', sa.Boolean(), nullable=False, server_default=sa.text('false'),
    ))
    op.add_column('users', sa.Column('subscription_source', sa.String(20), nullable=True))
    op.add_column('users', sa.Column('revenuecat_app_user_id', sa.String(100), nullable=True))
    op.add_column('users', sa.Column('billing_issue_at', sa.DateTime(), nullable=True))
    op.create_index('ix_users_revenuecat_app_user_id', 'users', ['revenuecat_app_user_id'], unique=True)

    # 2. Backfill trial_expires_at for existing users
    # Hardcoded to 14 days (the default at time of migration); future trial duration changes apply only to new users
    op.execute(
        "UPDATE users SET trial_expires_at = created_at + INTERVAL '14 days' "
        "WHERE trial_expires_at IS NULL"
    )

    # 3. Drop server_defaults (ORM handles defaults for new rows)
    op.alter_column('users', 'subscription_active', server_default=None)
    op.alter_column('users', 'subscription_will_renew', server_default=None)

    # 4. Create consumed_addon_transactions table
    op.create_table(
        'consumed_addon_transactions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('receipt_token', sa.String(512), nullable=False, unique=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_id', sa.String(100), nullable=False),
        sa.Column('platform', sa.String(20), nullable=False),
        sa.Column('credits_granted', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    # receipt_token already has a unique index from unique=True; no additional index needed
    op.create_index('ix_consumed_addon_tx_user', 'consumed_addon_transactions', ['user_id'])
    op.create_check_constraint('ck_addon_credits_positive', 'consumed_addon_transactions', 'credits_granted > 0')
    op.create_check_constraint('ck_addon_valid_platform', 'consumed_addon_transactions', "platform IN ('ios', 'android')")

    # 5. Create webhook_events table
    op.create_table(
        'webhook_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('event_id', sa.String(255), nullable=False, unique=True),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('processed_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    # event_id already has a unique index from unique=True; add index on processed_at for cleanup queries
    op.create_index('ix_webhook_events_processed_at', 'webhook_events', ['processed_at'])


def downgrade():
    op.drop_table('webhook_events')
    op.drop_table('consumed_addon_transactions')
    op.drop_index('ix_users_revenuecat_app_user_id', table_name='users')
    op.drop_column('users', 'billing_issue_at')
    op.drop_column('users', 'revenuecat_app_user_id')
    op.drop_column('users', 'subscription_source')
    op.drop_column('users', 'subscription_will_renew')
    op.drop_column('users', 'subscription_expires_at')
    op.drop_column('users', 'subscription_plan')
    op.drop_column('users', 'subscription_active')
    op.drop_column('users', 'trial_expires_at')
