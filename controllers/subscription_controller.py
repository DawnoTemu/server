import hmac
import logging
from datetime import datetime

from config import Config
from database import db
from models.user_model import User
from models.webhook_event_model import WebhookEvent
from models.credit_model import grant as credit_grant


logger = logging.getLogger(__name__)

STORE_MAP = {
    "APP_STORE": "app_store",
    "MAC_APP_STORE": "app_store",
    "PLAY_STORE": "play_store",
}


class SubscriptionController:

    @staticmethod
    def get_subscription_status(user):
        trial_active = user.trial_is_active
        subscription_active = bool(user.subscription_active)
        can_generate = subscription_active or trial_active

        days_remaining = 0
        if user.trial_expires_at and trial_active:
            delta = user.trial_expires_at - datetime.utcnow()
            days_remaining = max(0, delta.days)

        return True, {
            "trial": {
                "active": trial_active,
                "expires_at": user.trial_expires_at.isoformat() if user.trial_expires_at else None,
                "days_remaining": days_remaining,
            },
            "subscription": {
                "active": subscription_active,
                "plan": user.subscription_plan,
                "expires_at": (
                    user.subscription_expires_at.isoformat()
                    if user.subscription_expires_at
                    else None
                ),
                "will_renew": bool(user.subscription_will_renew),
            },
            "can_generate": can_generate,
            "initial_credits": Config.INITIAL_CREDITS,
        }, 200

    @staticmethod
    def handle_revenuecat_webhook(payload):
        event = payload.get("event")
        if not event or not isinstance(event, dict):
            return False, {"error": "Missing event object"}, 400

        event_type = event.get("type", "")
        event_id = event.get("id", "")
        app_user_id = str(event.get("app_user_id", ""))

        if not event_id:
            return False, {"error": "Missing event id"}, 400

        # TEST events need no processing
        if event_type == "TEST":
            logger.info("Received TEST webhook event")
            return True, {"status": "ok"}, 200

        # Idempotency: check if we already processed this event
        existing = WebhookEvent.query.filter_by(event_id=event_id).first()
        if existing:
            logger.info("Duplicate webhook event %s, skipping", event_id)
            return True, {"status": "already_processed"}, 200

        # User lookup
        user = User.query.filter_by(revenuecat_app_user_id=app_user_id).first()
        if not user:
            logger.warning(
                "Webhook event %s for unknown user %s (type=%s)",
                event_id, app_user_id, event_type,
            )
            # Record the event to prevent retries, return 200 so RevenueCat stops
            _record_event(event_id, event_type)
            return True, {"status": "user_not_found"}, 200

        # Dispatch by event type
        handler = _EVENT_HANDLERS.get(event_type)
        if handler:
            handler(user, event)
        else:
            logger.info("Unhandled webhook event type: %s", event_type)

        _record_event(event_id, event_type)

        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            logger.error("Failed to commit webhook event %s: %s", event_id, exc)
            return False, {"error": "Internal error"}, 500

        return True, {"status": "processed"}, 200


def _record_event(event_id, event_type):
    db.session.add(WebhookEvent(event_id=event_id, event_type=event_type))


def _handle_initial_purchase(user, event):
    product_id = event.get("product_id", "")
    store = event.get("store", "")
    expiration_ms = event.get("expiration_at_ms")

    user.subscription_active = True
    user.subscription_plan = product_id or "monthly"
    user.subscription_will_renew = True
    user.subscription_source = STORE_MAP.get(store, store.lower() if store else None)

    if expiration_ms:
        user.subscription_expires_at = datetime.utcfromtimestamp(expiration_ms / 1000.0)

    # Grant credits based on plan type
    _grant_subscription_credits(user, product_id, "initial_purchase")


def _handle_renewal(user, event):
    expiration_ms = event.get("expiration_at_ms")
    if expiration_ms:
        user.subscription_expires_at = datetime.utcfromtimestamp(expiration_ms / 1000.0)

    user.subscription_active = True
    user.subscription_will_renew = True

    product_id = event.get("product_id", "")
    _grant_subscription_credits(user, product_id, "renewal")


def _handle_cancellation(user, event):
    user.subscription_will_renew = False


def _handle_expiration(user, event):
    user.subscription_active = False
    user.subscription_will_renew = False


def _handle_billing_issue(user, event):
    logger.warning("Billing issue for user %s: %s", user.id, event.get("id"))


def _handle_product_change(user, event):
    new_product = event.get("new_product_id") or event.get("product_id")
    if new_product:
        user.subscription_plan = new_product


YEARLY_PRODUCT_IDS = {"dawnotemu_annual", "dawnotemu_yearly"}


def _grant_subscription_credits(user, product_id, reason):
    if product_id in YEARLY_PRODUCT_IDS:
        amount = Config.YEARLY_SUBSCRIPTION_MONTHLY_CREDITS
    else:
        amount = Config.MONTHLY_SUBSCRIPTION_CREDITS
    if amount <= 0:
        return
    try:
        credit_grant(
            user_id=user.id,
            amount=amount,
            reason=f"subscription_{reason}",
            source="monthly",
            expires_at=None,
        )
    except Exception as exc:
        logger.error("Failed to grant subscription credits for user %s: %s", user.id, exc)


_EVENT_HANDLERS = {
    "INITIAL_PURCHASE": _handle_initial_purchase,
    "RENEWAL": _handle_renewal,
    "CANCELLATION": _handle_cancellation,
    "EXPIRATION": _handle_expiration,
    "BILLING_ISSUE": _handle_billing_issue,
    "PRODUCT_CHANGE": _handle_product_change,
}
