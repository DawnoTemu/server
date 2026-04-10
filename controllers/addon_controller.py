"""
Addon credit pack grants.

IMPORTANT — RevenueCat API version mismatch (see server#44):

The mobile SDK (react-native-purchases v9) exposes
``nonSubscriptionTransactions[i].transactionIdentifier`` as the
*RevenueCat v1-format internal id* (e.g. ``o1_kSFvmriDAHzQ1wdJi0UAhg``).
This is NOT the Apple store transaction id and NOT the RC v2 internal id.

The v2 API (``/v2/projects/.../customers/.../purchases``) does not expose
the v1 id as any field. Attempting to validate the mobile's receipt_token
against v2 data always fails — which is exactly what happened in
production before this file was fixed (see ``_validate_receipt_with_revenuecat``).

If you are adding server-side code that consumes any field from
``customerInfo.nonSubscriptionTransactions``, you MUST use RC v1
(``/v1/subscribers/{app_user_id}``). Do not mix v1 and v2 in the same
request path.
"""

import logging
import os

import requests
from sqlalchemy.exc import IntegrityError

from config import Config
from database import db
from models.addon_transaction_model import ConsumedAddonTransaction
from models.credit_model import grant as credit_grant

logger = logging.getLogger(__name__)

ADDON_PRODUCTS = {
    "credits_10": 10,
    "credits_20": 20,
    "credits_30": 30,
}

VALID_PLATFORMS = {"ios", "android"}


class ReceiptValidationUnavailable(Exception):
    """Raised when receipt validation cannot be performed due to transient errors."""


def _validate_receipt_with_revenuecat(user, receipt_token, expected_product_id, platform):
    """Verify the non-subscription transaction exists in RevenueCat for this
    user AND that it belongs to *expected_product_id*.

    Uses RevenueCat's v1 API (``/v1/subscribers/{app_user_id}``) because the
    mobile SDK's ``nonSubscriptionTransactions[i].transactionIdentifier`` field
    returns the v1-format internal id (e.g. ``o1_kSFvmriDAHzQ1wdJi0UAhg``),
    which the v2 API does not expose. Matching would always fail if we queried
    v2, which is what happened in production before this fix.

    The v1 ``non_subscriptions`` response groups transactions by product_id, so
    the product-mismatch check is implicit: if the client claims ``credits_30``
    but the receipt is filed under ``credits_10``, we simply won't find it in
    ``non_subscriptions['credits_30']`` and the function returns False. This
    preserves the security guarantee from PR #42 (a valid ``credits_10``
    receipt cannot be redeemed as ``credits_30``).

    Returns True only when the receipt is found under the expected product.
    Raises ReceiptValidationUnavailable on transient errors (network, 5xx, 429).
    Returns False if the receipt is not found, product does not match, or auth
    is not configured in production.

    Uses a platform-specific public key (``REVENUECAT_IOS_PUBLIC_KEY`` /
    ``REVENUECAT_ANDROID_PUBLIC_KEY``) because the v1 API does not accept v2
    secret keys. These are the same public keys baked into the mobile app.
    """
    if platform == "ios":
        api_key = Config.REVENUECAT_IOS_PUBLIC_KEY
        key_name = "REVENUECAT_IOS_PUBLIC_KEY"
    elif platform == "android":
        api_key = Config.REVENUECAT_ANDROID_PUBLIC_KEY
        key_name = "REVENUECAT_ANDROID_PUBLIC_KEY"
    else:
        logger.error("Unknown platform for receipt validation: %r (user=%s)", platform, user.id)
        return False

    if not api_key:
        env = os.getenv("FLASK_ENV", "") or os.getenv("ENVIRONMENT", "")
        if env.lower() in ("development", "testing", "test"):
            logger.warning("%s not configured; skipping receipt validation (dev mode)", key_name)
            return True
        logger.error("%s not configured — rejecting receipt (env=%s)", key_name, env)
        return False

    rc_user_id = getattr(user, "revenuecat_app_user_id", None)
    if not rc_user_id:
        logger.warning("User %s has no revenuecat_app_user_id; cannot validate receipt", user.id)
        return False

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Platform": platform,
    }

    url = f"https://api.revenuecat.com/v1/subscribers/{rc_user_id}"

    try:
        resp = requests.get(url, headers=headers, timeout=10)
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
        logger.error("RevenueCat v1 transient error for user %s: %s", user.id, exc)
        raise ReceiptValidationUnavailable(
            "Receipt validation service temporarily unavailable"
        ) from exc

    if resp.status_code != 200:
        logger.error(
            "RevenueCat v1 subscribers lookup failed: %s %s",
            resp.status_code, resp.text[:200],
        )
        if resp.status_code >= 500 or resp.status_code == 429:
            raise ReceiptValidationUnavailable(
                f"RevenueCat v1 returned {resp.status_code}"
            )
        return False

    try:
        data = resp.json()
    except (ValueError, requests.exceptions.JSONDecodeError) as exc:
        logger.error(
            "RevenueCat v1 returned non-JSON response (status=%s): %s",
            resp.status_code, resp.text[:200],
        )
        raise ReceiptValidationUnavailable("RevenueCat v1 returned invalid JSON") from exc

    non_subscriptions = (
        (data.get("subscriber") or {}).get("non_subscriptions") or {}
    )

    # v1 groups non_subscriptions BY product_id. Looking up under the expected
    # product is the product-mismatch check: if the client claims credits_30
    # but bought credits_10, the receipt_token will not appear under the
    # credits_30 bucket.
    product_transactions = non_subscriptions.get(expected_product_id) or []
    for tx in product_transactions:
        # Match on v1 internal id (what the mobile SDK returns) OR on
        # store_transaction_id (the Apple/Google store transaction id), so
        # the function keeps working if the mobile SDK changes behavior.
        if tx.get("id") == receipt_token or tx.get("store_transaction_id") == receipt_token:
            return True

    logger.warning(
        "Receipt not found under product %s for user %s in RevenueCat v1",
        expected_product_id, user.id,
    )
    return False


class AddonController:

    @staticmethod
    def grant_addon(user, receipt_token, product_id, platform):
        if not receipt_token or not product_id or not platform:
            return False, {"error": "Missing required fields"}, 400

        if product_id not in ADDON_PRODUCTS:
            return False, {"error": f"Unknown product: {product_id}"}, 400

        if platform not in VALID_PLATFORMS:
            return False, {"error": f"Invalid platform: {platform}"}, 400

        if not user.subscription_is_active:
            return False, {"error": "Active subscription required"}, 403

        existing = ConsumedAddonTransaction.query.filter_by(
            receipt_token=receipt_token
        ).first()

        if existing:
            if existing.user_id == user.id:
                return True, {
                    "credits_granted": existing.credits_granted,
                    "new_balance": user.credits_balance,
                }, 200
            return False, {"error": "Transaction already consumed by another account"}, 409

        try:
            if not _validate_receipt_with_revenuecat(user, receipt_token, product_id, platform):
                return False, {"error": "Receipt validation failed"}, 403
        except ReceiptValidationUnavailable:
            return False, {"error": "Receipt validation temporarily unavailable, please retry"}, 503
        except Exception as exc:
            logger.error("Receipt validation unexpected error for user %s: %s", user.id, exc, exc_info=True)
            return False, {"error": "Receipt validation failed"}, 500

        credits_amount = ADDON_PRODUCTS[product_id]

        # Insert the transaction record FIRST to claim the receipt_token via
        # unique constraint.  This prevents the race where two concurrent
        # requests both pass the existence check, both grant credits, and one
        # rolls back — leaving the user with orphaned credits.
        tx = ConsumedAddonTransaction(
            receipt_token=receipt_token,
            user_id=user.id,
            product_id=product_id,
            platform=platform,
            credits_granted=credits_amount,
        )
        try:
            db.session.add(tx)
            db.session.flush()  # Triggers unique constraint check
        except IntegrityError:
            db.session.rollback()
            dup = ConsumedAddonTransaction.query.filter_by(receipt_token=receipt_token).first()
            if dup and dup.user_id == user.id:
                db.session.refresh(user)
                return True, {
                    "credits_granted": dup.credits_granted,
                    "new_balance": user.credits_balance,
                }, 200
            return False, {"error": "Transaction already consumed by another account"}, 409

        # Now grant credits — the receipt is already claimed, so no other
        # request can double-grant even if this fails and retries.
        try:
            credit_grant(
                user_id=user.id,
                amount=credits_amount,
                reason=f"addon:{product_id}",
                source="add_on",
                expires_at=None,
            )
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            logger.error("Addon grant failed for user %s: %s", user.id, exc, exc_info=True)
            return False, {"error": "Failed to grant credits"}, 500

        db.session.refresh(user)

        return True, {
            "credits_granted": credits_amount,
            "new_balance": user.credits_balance,
        }, 200
