import logging
from datetime import datetime, timedelta

from celery.schedules import crontab

from tasks import celery_app
from database import db
from config import Config
from models.user_model import User
from models.credit_model import CreditLot, grant as credit_grant

logger = logging.getLogger('billing_tasks')


@celery_app.task(name='billing.grant_monthly_credits', ignore_result=True)
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

    now = datetime.utcnow()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # Compute next month start
    if start_of_month.month == 12:
        next_month = start_of_month.replace(year=start_of_month.year + 1, month=1)
    else:
        next_month = start_of_month.replace(month=start_of_month.month + 1)

    users = db.session.query(User).filter(User.is_active.is_(True)).all()
    granted = 0
    for u in users:
        # Check if user already has a monthly lot created this month
        existing = (
            db.session.query(CreditLot)
            .filter(
                CreditLot.user_id == u.id,
                CreditLot.source == 'monthly',
                CreditLot.created_at >= start_of_month,
                CreditLot.created_at < next_month,
            )
            .first()
        )
        if existing:
            continue
        try:
            credit_grant(u.id, amount, reason='monthly_grant', source='monthly', expires_at=None)
            granted += 1
        except Exception as e:
            logger.error('Failed granting monthly credits to user %s: %s', u.id, e)
    logger.info('Monthly credit grant complete. Users granted: %s', granted)


# Register Celery beat schedule (runs daily at 03:00 UTC)
celery_app.conf.beat_schedule = getattr(celery_app.conf, 'beat_schedule', {}) | {
    'monthly-credits-daily-check': {
        'task': 'billing.grant_monthly_credits',
        'schedule': crontab(minute=0, hour=3),
    }
}

