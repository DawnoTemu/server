import logging
from datetime import datetime, timedelta

from celery.schedules import crontab

from tasks import celery_app, FlaskTask
from database import db
from config import Config
from models.user_model import User
from models.credit_model import (
    CreditLot,
    CreditTransaction,
    CreditTransactionAllocation,
    grant as credit_grant,
)
from utils.time_utils import utc_now

logger = logging.getLogger('billing_tasks')


@celery_app.task(name='billing.grant_monthly_credits', base=FlaskTask, ignore_result=True)
def grant_monthly_credits():
    """Daily scheduler task that grants monthly Story Points to eligible users.

    MVP behavior:
    - Reads amount from Config.MONTHLY_CREDITS_DEFAULT (0 => disabled).
    - For each user, if no `monthly` lot exists in the current month, grant one.
    - Lots are non-expiring for now (expires_at=None). Future: set a monthly expiry.
    """
    amount = int(getattr(Config, 'MONTHLY_CREDITS_DEFAULT', 0) or 0)
    if amount <= 0:
        logger.info('Monthly credit grants disabled (amount=%s). Skipping.', amount)
        return

    now = utc_now()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # Compute next month start
    if start_of_month.month == 12:
        next_month = start_of_month.replace(year=start_of_month.year + 1, month=1)
    else:
        next_month = start_of_month.replace(month=start_of_month.month + 1)

    user_ids = [uid for (uid,) in db.session.query(User.id).filter(User.is_active.is_(True)).all()]
    granted = 0
    failed = 0
    for uid in user_ids:
        # Check if user already has a monthly lot created this month
        existing = (
            db.session.query(CreditLot)
            .filter(
                CreditLot.user_id == uid,
                CreditLot.source == 'monthly',
                CreditLot.created_at >= start_of_month,
                CreditLot.created_at < next_month,
            )
            .first()
        )
        if existing:
            continue
        try:
            credit_grant(uid, amount, reason='monthly_grant', source='monthly', expires_at=None)
            granted += 1
        except Exception as e:
            db.session.rollback()
            failed += 1
            logger.error('Failed granting monthly credits to user %s: %s', uid, e, exc_info=True)

    logger.info('Monthly credit grant complete. Granted: %s, failed: %s', granted, failed)

    if failed > 0 and (failed / max(granted + failed, 1)) > 0.1:
        raise RuntimeError(
            f"Monthly credit grant failure rate too high: {failed}/{granted + failed}"
        )


# Register Celery beat schedule (runs daily at 03:00 UTC)
_existing_schedule = getattr(celery_app.conf, 'beat_schedule', None) or {}
celery_app.conf.beat_schedule = {
    **_existing_schedule,
    'monthly-credits-daily-check': {
        'task': 'billing.grant_monthly_credits',
        'schedule': crontab(minute=0, hour=3),
    },
}


@celery_app.task(name='billing.grant_yearly_subscriber_monthly_credits', base=FlaskTask, ignore_result=True)
def grant_yearly_subscriber_monthly_credits():
    """Daily scheduler task that grants monthly credits to yearly subscribers.

    Yearly subscribers receive one RevenueCat INITIAL_PURCHASE event per year,
    but should get credits every month.  This task finds active yearly
    subscribers who have not yet received a monthly lot this calendar month
    and grants them their credits (YEARLY_SUBSCRIPTION_MONTHLY_CREDITS, default 30).

    The webhook handler also grants credits on INITIAL_PURCHASE; the
    duplicate-lot check prevents double-granting in the same calendar month.
    """
    amount = int(getattr(Config, 'YEARLY_SUBSCRIPTION_MONTHLY_CREDITS', 30) or 30)
    if amount <= 0:
        logger.info('Yearly monthly credit grants disabled (amount=%s).', amount)
        return

    now = utc_now()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start_of_month.month == 12:
        next_month = start_of_month.replace(year=start_of_month.year + 1, month=1)
    else:
        next_month = start_of_month.replace(month=start_of_month.month + 1)

    # Find active yearly subscribers whose subscription has not expired
    yearly_user_ids = [
        uid for (uid,) in
        db.session.query(User.id)
        .filter(
            User.is_active.is_(True),
            User.subscription_active.is_(True),
            User.subscription_plan.in_(Config.YEARLY_PRODUCT_IDS),
            User.subscription_expires_at.isnot(None),
            User.subscription_expires_at > now,
        )
        .all()
    ]

    granted = 0
    failed = 0
    for uid in yearly_user_ids:
        # Skip if already granted this month
        existing = (
            db.session.query(CreditLot)
            .filter(
                CreditLot.user_id == uid,
                CreditLot.source == 'monthly',
                CreditLot.created_at >= start_of_month,
                CreditLot.created_at < next_month,
            )
            .first()
        )
        if existing:
            continue
        try:
            credit_grant(
                uid, amount,
                reason='yearly_subscription_monthly_grant',
                source='monthly',
                expires_at=None,
            )
            granted += 1
        except Exception as e:
            db.session.rollback()
            failed += 1
            logger.error('Failed granting yearly monthly credits to user %s: %s', uid, e, exc_info=True)

    logger.info(
        'Yearly subscriber monthly credit grant complete. Granted: %s/%s, failed: %s',
        granted, len(yearly_user_ids), failed,
    )

    if failed > 0 and (failed / max(granted + failed, 1)) > 0.1:
        raise RuntimeError(
            f"Yearly monthly credit grant failure rate too high: {failed}/{granted + failed}"
        )


@celery_app.task(name='billing.expire_credit_lots', base=FlaskTask, ignore_result=True)
def expire_credit_lots():
    """Daily job to expire credit lots at or before now and adjust balances.

    Behavior:
    - Finds lots where expires_at <= now AND amount_remaining > 0.
    - Zeros out amount_remaining for those lots.
    - Records ledger entries (CreditTransaction + allocations) describing each expiry.
    - Decreases users.credits_balance by the total amount removed per user (not below 0).
    """
    now = utc_now()
    query = (
        db.session.query(CreditLot)
        .filter(
            CreditLot.expires_at.isnot(None),
            CreditLot.expires_at <= now,
            CreditLot.amount_remaining > 0,
        )
    )
    # Use row-level locks when supported to avoid racing concurrent debits
    dialect_name = None
    try:
        bind = getattr(db.session, "get_bind", lambda: None)()
        dialect_name = getattr(getattr(bind, "dialect", None), "name", None)
    except (AttributeError, TypeError):
        logger.warning("Could not determine dialect for row locking; proceeding without FOR UPDATE", exc_info=True)
        dialect_name = None
    if hasattr(query, "with_for_update") and dialect_name not in (None, "sqlite"):
        query = query.with_for_update()
    expired_lots = query.all()
    if not expired_lots:
        logger.info('No expiring credit lots found.')
        return

    delta_by_user: dict[int, int] = {}
    for lot in expired_lots:
        amt = int(lot.amount_remaining or 0)
        if amt <= 0:
            continue
        tx = CreditTransaction(
            user_id=lot.user_id,
            amount=-amt,
            type='expire',
            reason='auto_expire',
            audio_story_id=None,
            story_id=None,
            status='applied',
            metadata_json={
                'lot_id': lot.id,
                'lot_source': lot.source,
                'lot_amount_granted': int(lot.amount_granted or 0),
                'expired_at': now.isoformat(),
                'source_task': 'billing.expire_credit_lots',
            },
        )
        allocation = CreditTransactionAllocation(transaction=tx, lot=lot, amount=-amt)
        db.session.add(tx)
        db.session.add(allocation)
        lot.amount_remaining = 0
        delta_by_user[lot.user_id] = delta_by_user.get(lot.user_id, 0) + amt

    # Apply balance adjustments
    for user_id, delta in delta_by_user.items():
        user = db.session.get(User, user_id)
        if not user:
            logger.warning("User %s not found during credit lot expiration — skipping balance adjustment", user_id)
            continue
        curr = int(user.credits_balance or 0)
        new_val = max(0, curr - delta)
        user.credits_balance = new_val

    try:
        db.session.commit()
        logger.info('Expired %d lots; adjusted %d users.', len(expired_lots), len(delta_by_user))
    except Exception as e:
        db.session.rollback()
        logger.error('Error expiring credit lots: %s', e, exc_info=True)
        raise


@celery_app.task(name='billing.cleanup_old_webhook_events', base=FlaskTask, ignore_result=True)
def cleanup_old_webhook_events():
    """Prune ``webhook_events`` rows older than ``WEBHOOK_EVENT_RETENTION_DAYS``.

    The ``webhook_events`` table is append-only and used only for idempotency
    on incoming RevenueCat webhook deliveries. Events that are older than the
    retention window will never be re-delivered by RevenueCat (their retry
    window is ~72 hours), so keeping them around is pure storage overhead.

    Default retention: 90 days. Override via the
    ``WEBHOOK_EVENT_RETENTION_DAYS`` environment variable. 0 disables the
    task (useful for disabling pruning in environments that want full
    historical data).

    Uses a bulk ``DELETE`` keyed on the indexed ``processed_at`` column so
    the operation is fast even on large tables. Commits in a single
    transaction; rolls back cleanly on error.
    """
    # Local import to avoid a circular dependency at module load.
    from models.webhook_event_model import WebhookEvent

    retention_days = getattr(Config, 'WEBHOOK_EVENT_RETENTION_DAYS', 90)
    if retention_days is None:
        retention_days = 90
    if retention_days <= 0:
        logger.info('Webhook event cleanup disabled (retention_days=%s)', retention_days)
        return

    cutoff = utc_now() - timedelta(days=retention_days)
    try:
        deleted = db.session.query(WebhookEvent).filter(
            WebhookEvent.processed_at < cutoff
        ).delete(synchronize_session=False)
        db.session.commit()
        logger.info(
            'Pruned %d webhook_events rows older than %s (retention=%d days)',
            deleted, cutoff.isoformat(timespec='seconds'), retention_days,
        )
    except Exception as exc:
        db.session.rollback()
        logger.error('Failed to prune old webhook_events: %s', exc, exc_info=True)
        raise


# Schedule the expiration sweeper daily at 03:15 UTC
_existing_schedule = getattr(celery_app.conf, 'beat_schedule', None) or {}
celery_app.conf.beat_schedule = {
    **_existing_schedule,
    'expire-credit-lots-daily': {
        'task': 'billing.expire_credit_lots',
        'schedule': crontab(minute=15, hour=3),
    },
    'yearly-subscriber-monthly-credits': {
        'task': 'billing.grant_yearly_subscriber_monthly_credits',
        'schedule': crontab(minute=30, hour=3),  # daily at 03:30 UTC
    },
    'cleanup-old-webhook-events': {
        'task': 'billing.cleanup_old_webhook_events',
        'schedule': crontab(minute=45, hour=3),  # daily at 03:45 UTC
    },
}
