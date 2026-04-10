import logging
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError

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

_KNOWN_SOURCES = frozenset(STORE_MAP.values())

# Reasonable bounds for expiration timestamps (2020-01-01 to 2100-01-01 in ms)
_MIN_EXPIRATION_MS = 1_577_836_800_000
_MAX_EXPIRATION_MS = 4_102_444_800_000


def _parse_expiration_ms(value):
    """Parse and validate expiration_at_ms from a webhook event.

    Returns a datetime on success or None if the value is missing/invalid.
    """
    if value is None:
        return None
    try:
        ms = int(value)
    except (TypeError, ValueError):
        logger.error("expiration_at_ms is not numeric: %r", value)
        return None
    if ms <= 0:
        logger.error("expiration_at_ms is non-positive: %s", ms)
        return None
    if ms < _MIN_EXPIRATION_MS or ms > _MAX_EXPIRATION_MS:
        logger.error("expiration_at_ms out of range: %s", ms)
        return None
    return datetime.utcfromtimestamp(ms / 1000.0)


def _resolve_store_source(store):
    """Map a RevenueCat store string to a known subscription_source value.

    Returns a known source string or None for empty/unmappable values.
    """
    if not store:
        return None
    mapped = STORE_MAP.get(store)
    if mapped:
        return mapped
    # Unknown store — log and return None rather than saving dirty data
    logger.warning("Unknown store value in webhook: %r — ignoring", store)
    return None


class SubscriptionController:

    @staticmethod
    def get_subscription_status(user):
        can_generate = user.can_generate

        days_remaining = 0
        if user.trial_expires_at and user.trial_is_active:
            delta = user.trial_expires_at - datetime.utcnow()
            days_remaining = max(0, delta.days)

        return True, {
            "trial": {
                "active": user.trial_is_active,
                "expires_at": user.trial_expires_at.isoformat() if user.trial_expires_at else None,
                "days_remaining": days_remaining,
            },
            "subscription": {
                "active": user.subscription_is_active,
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

        # RevenueCat sends TEST events during webhook setup verification
        if event_type == "TEST":
            logger.info("Received TEST webhook event")
            return True, {"status": "ok"}, 200

        # User lookup FIRST — return 404 before recording the event so
        # RevenueCat retries without any DB state to clean up.
        user = User.query.filter_by(revenuecat_app_user_id=app_user_id).first()
        if not user:
            logger.warning(
                "Webhook event %s for unknown user %s (type=%s)",
                event_id, app_user_id, event_type,
            )
            return False, {"error": "user_not_found"}, 404

        # --- Idempotency via INSERT race ---
        # Attempt the insert directly rather than SELECT-then-INSERT (TOCTOU).
        # If a concurrent request already inserted the same event_id the
        # IntegrityError tells us it was already handled.
        try:
            _record_event(event_id, event_type)
        except IntegrityError:
            db.session.rollback()
            logger.info("Duplicate webhook event %s, skipping", event_id)
            return True, {"status": "already_processed"}, 200

        handler = _EVENT_HANDLERS.get(event_type)
        if not handler:
            # Event already recorded above; just commit and return 200.
            logger.warning("Unhandled webhook event type: %s (event_id=%s)", event_type, event_id)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                logger.debug("Duplicate unhandled event %s", event_id)
            return True, {"status": "ignored"}, 200

        try:
            handler(user, event)
        except Exception as exc:
            db.session.rollback()
            logger.error(
                "Handler %s failed for event %s (user_id=%s, product_id=%s): %s",
                event_type, event_id, user.id, event.get("product_id", "?"), exc,
                exc_info=True,
            )
            return False, {"error": "Internal error"}, 500

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            logger.info("Concurrent duplicate webhook event %s", event_id)
            return True, {"status": "already_processed"}, 200
        except Exception as exc:
            db.session.rollback()
            logger.error("Failed to commit webhook event %s: %s", event_id, exc, exc_info=True)
            return False, {"error": "Internal error"}, 500

        return True, {"status": "processed"}, 200

    @staticmethod
    def link_revenuecat(user, revenuecat_app_user_id):
        """Bind the authenticated user's server-side ID as their RevenueCat
        app_user_id.

        SECURITY: The RC app_user_id is derived from the authenticated user's
        server-side id, NOT from client input. Allowing the client to supply
        an arbitrary value would let a malicious client pre-claim another
        user's predictable RC id (e.g. str(user.id)) and hijack webhook
        attribution for that account.

        If the client supplies a value, it must equal str(user.id); otherwise
        the request is rejected so buggy clients surface the mismatch instead
        of silently using the wrong id.
        """
        authoritative_id = str(user.id)

        if revenuecat_app_user_id is not None:
            client_supplied = (revenuecat_app_user_id or "").strip()
            if client_supplied and client_supplied != authoritative_id:
                logger.warning(
                    "link_revenuecat: client supplied id=%r does not match authenticated user=%s",
                    client_supplied[:50], user.id,
                )
                return False, {"error": "revenuecat_app_user_id must match authenticated user"}, 400

        # Idempotent: already linked correctly
        if user.revenuecat_app_user_id == authoritative_id:
            return True, {"status": "linked", "revenuecat_app_user_id": authoritative_id}, 200

        # A different user already holds this ID — should be impossible since
        # authoritative_id is unique per user, but defend against corrupted state.
        conflict = User.query.filter(
            User.revenuecat_app_user_id == authoritative_id,
            User.id != user.id,
        ).first()
        if conflict:
            logger.error(
                "link_revenuecat: RC id %s already linked to user %s (current user=%s) — data corruption",
                authoritative_id, conflict.id, user.id,
            )
            return False, {"error": "RevenueCat ID already linked to another account"}, 409

        user.revenuecat_app_user_id = authoritative_id
        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            logger.error("Failed to link RevenueCat ID for user %s: %s", user.id, exc, exc_info=True)
            return False, {"error": "Failed to link account"}, 500

        return True, {"status": "linked", "revenuecat_app_user_id": authoritative_id}, 200


def _record_event(event_id, event_type):
    db.session.add(WebhookEvent(event_id=event_id, event_type=event_type))
    db.session.flush()


def _handle_initial_purchase(user, event):
    product_id = event.get("product_id", "")
    store = event.get("store", "")

    user.subscription_active = True
    user.subscription_plan = product_id or None
    user.subscription_will_renew = True
    user.billing_issue_at = None
    user.subscription_source = _resolve_store_source(store)

    parsed_expiry = _parse_expiration_ms(event.get("expiration_at_ms"))
    if parsed_expiry:
        user.subscription_expires_at = parsed_expiry
    else:
        fallback = datetime.utcnow() + timedelta(days=35)
        user.subscription_expires_at = fallback
        logger.error(
            "INITIAL_PURCHASE for user %s has no valid expiration_at_ms — using 35-day fallback (%s)",
            user.id, fallback.isoformat(),
        )

    _grant_subscription_credits(user, product_id, "initial_purchase")


def _handle_renewal(user, event):
    parsed_expiry = _parse_expiration_ms(event.get("expiration_at_ms"))
    if parsed_expiry:
        user.subscription_expires_at = parsed_expiry
    else:
        fallback = datetime.utcnow() + timedelta(days=35)
        user.subscription_expires_at = fallback
        logger.error(
            "RENEWAL for user %s has no valid expiration_at_ms — using 35-day fallback (%s)",
            user.id, fallback.isoformat(),
        )

    user.subscription_active = True
    user.subscription_will_renew = True
    user.billing_issue_at = None

    product_id = event.get("product_id", "")
    _grant_subscription_credits(user, product_id, "renewal")


def _handle_cancellation(user, event):
    user.subscription_will_renew = False


def _handle_uncancellation(user, event):
    user.subscription_will_renew = True
    user.billing_issue_at = None


def _handle_expiration(user, event):
    user.subscription_active = False
    user.subscription_will_renew = False
    user.billing_issue_at = None


def _handle_billing_issue(user, event):
    logger.warning("Billing issue for user %s: %s", user.id, event.get("id"))
    user.billing_issue_at = datetime.utcnow()


def _handle_product_change(user, event):
    # Credits are NOT granted here: the billing cycle does not reset on a plan
    # change, so the user keeps their current month's credits.  The next
    # RENEWAL event will grant credits at the new plan's rate.
    new_product = event.get("new_product_id") or event.get("product_id")
    if not new_product:
        logger.warning(
            "PRODUCT_CHANGE event for user %s has no product identifier: %s",
            user.id, event.get("id"),
        )
        return
    user.subscription_plan = new_product

    parsed_expiry = _parse_expiration_ms(event.get("expiration_at_ms"))
    if parsed_expiry:
        user.subscription_expires_at = parsed_expiry
    else:
        logger.warning(
            "PRODUCT_CHANGE for user %s has no expiration_at_ms — keeping current expiration",
            user.id,
        )


def _grant_subscription_credits(user, product_id, reason):
    if product_id in Config.YEARLY_PRODUCT_IDS:
        amount = Config.YEARLY_SUBSCRIPTION_MONTHLY_CREDITS
    else:
        amount = Config.MONTHLY_SUBSCRIPTION_CREDITS
    if amount <= 0:
        return
    # Let exceptions propagate so the webhook handler can rollback and return 500,
    # allowing RevenueCat to retry rather than permanently losing credits.
    credit_grant(
        user_id=user.id,
        amount=amount,
        reason=f"subscription_{reason}",
        source="monthly",
        expires_at=None,
    )


_EVENT_HANDLERS = {
    "INITIAL_PURCHASE": _handle_initial_purchase,
    "RENEWAL": _handle_renewal,
    "CANCELLATION": _handle_cancellation,
    "UNCANCELLATION": _handle_uncancellation,
    "EXPIRATION": _handle_expiration,
    "BILLING_ISSUE": _handle_billing_issue,
    "PRODUCT_CHANGE": _handle_product_change,
}
