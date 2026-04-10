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


def _validate_receipt_with_revenuecat(user, receipt_token, expected_product_id):
    """Verify the transaction exists in RevenueCat for this user AND that the
    matched purchase is for *expected_product_id*.

    Returns True only when both checks pass.
    Raises ReceiptValidationUnavailable on transient errors (network, timeout).
    Returns False if the receipt is not found or the product does not match.

    When REVENUECAT_API_KEY is not configured, returns True only in
    non-production environments (allowing development without RevenueCat).

    CRITICAL: This function MUST verify that the matched purchase is actually
    for the claimed product. Without this check, any valid purchase token for
    the customer can be redeemed as whichever add-on tier the caller names,
    which is a billing bypass (e.g. pay for credits_10, claim credits_30).
    """
    api_key = Config.REVENUECAT_API_KEY
    project_id = Config.REVENUECAT_PROJECT_ID
    if not api_key:
        env = os.getenv("FLASK_ENV", "") or os.getenv("ENVIRONMENT", "")
        if env.lower() in ("development", "testing", "test"):
            logger.warning("REVENUECAT_API_KEY not configured; skipping receipt validation (dev mode)")
            return True
        logger.error("REVENUECAT_API_KEY not configured — rejecting receipt (env=%s)", env)
        return False

    if not project_id:
        logger.error("REVENUECAT_PROJECT_ID not configured — cannot validate receipt")
        return False

    rc_user_id = getattr(user, "revenuecat_app_user_id", None)
    if not rc_user_id:
        logger.warning("User %s has no revenuecat_app_user_id; cannot validate receipt", user.id)
        return False

    # TEMP DEBUG — remove after diagnosing mobile receipt_token mismatch
    logger.info(
        "DEBUG_RECEIPT_TOKEN: user=%s rc_user_id=%s expected_product=%s receipt_token=%r (len=%d)",
        user.id, rc_user_id, expected_product_id, receipt_token, len(receipt_token or ""),
    )

    _MAX_PAGES = 5  # Safety limit to prevent infinite pagination loops

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        url = f"https://api.revenuecat.com/v2/projects/{project_id}/customers/{rc_user_id}/purchases"

        for _page in range(_MAX_PAGES):
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                logger.error("RevenueCat purchases lookup failed: %s %s", resp.status_code, resp.text[:200])
                if resp.status_code >= 500 or resp.status_code == 429:
                    raise ReceiptValidationUnavailable(
                        f"RevenueCat returned {resp.status_code}"
                    )
                return False

            try:
                data = resp.json()
            except (ValueError, requests.exceptions.JSONDecodeError) as exc:
                logger.error("RevenueCat returned non-JSON response (status=%s): %s", resp.status_code, resp.text[:200])
                raise ReceiptValidationUnavailable("RevenueCat returned invalid response") from exc

            # v2 API returns {items: [{id, store_purchase_identifier, product_id, ...}]}
            # TEMP DEBUG — dump every purchase RC returns so we can compare identifiers
            _debug_items = data.get("items", [])
            logger.info(
                "DEBUG_RECEIPT_TOKEN: RC returned %d purchases for user %s",
                len(_debug_items), user.id,
            )
            for _i, _p in enumerate(_debug_items):
                logger.info(
                    "DEBUG_RECEIPT_TOKEN: [item %d] id=%r store_purchase_identifier=%r product_id=%r",
                    _i, _p.get("id"), _p.get("store_purchase_identifier"), _p.get("product_id"),
                )
            for purchase in data.get("items", []):
                store_id = str(purchase.get("store_purchase_identifier", ""))
                purchase_id = purchase.get("id", "")
                if receipt_token not in (store_id, purchase_id):
                    continue

                # Receipt matched — verify it's for the claimed product.
                rc_product_id = purchase.get("product_id")
                if not rc_product_id:
                    logger.error(
                        "Matched purchase has no product_id (user=%s receipt=%s)",
                        user.id, receipt_token[:20],
                    )
                    return False

                actual_store_id = _fetch_product_store_identifier(
                    project_id, rc_product_id, headers
                )
                if actual_store_id != expected_product_id:
                    logger.warning(
                        "Receipt product mismatch: expected=%s actual=%s user=%s receipt=%s",
                        expected_product_id, actual_store_id, user.id, receipt_token[:20],
                    )
                    return False

                return True

            # Follow pagination if more pages exist
            next_page = data.get("next_page")
            if not next_page:
                break
            url = f"https://api.revenuecat.com{next_page}"

        logger.warning("Receipt not found in RevenueCat for user %s", user.id)
        return False
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
        logger.error("RevenueCat transient error for user %s: %s", user.id, exc, exc_info=True)
        raise ReceiptValidationUnavailable("Receipt validation service temporarily unavailable") from exc
    except ReceiptValidationUnavailable:
        raise
    except Exception as exc:
        logger.error("RevenueCat receipt validation error for user %s: %s", user.id, exc, exc_info=True)
        raise ValueError(
            f"Receipt validation failed unexpectedly: {exc}"
        ) from exc


def _fetch_product_store_identifier(project_id, rc_product_id, headers):
    """Fetch a RevenueCat product by internal id and return its store_identifier.

    Raises ReceiptValidationUnavailable on transient errors.
    Returns None if the product cannot be resolved.
    """
    url = f"https://api.revenuecat.com/v2/projects/{project_id}/products/{rc_product_id}"
    try:
        resp = requests.get(url, headers=headers, timeout=10)
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
        raise ReceiptValidationUnavailable(
            f"Product lookup transient error: {exc}"
        ) from exc

    if resp.status_code != 200:
        if resp.status_code >= 500 or resp.status_code == 429:
            raise ReceiptValidationUnavailable(
                f"Product lookup returned {resp.status_code}"
            )
        logger.error(
            "Product lookup failed: %s %s (product=%s)",
            resp.status_code, resp.text[:200], rc_product_id,
        )
        return None

    try:
        data = resp.json()
    except (ValueError, requests.exceptions.JSONDecodeError) as exc:
        raise ReceiptValidationUnavailable("Product lookup returned invalid JSON") from exc

    return data.get("store_identifier")


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
            if not _validate_receipt_with_revenuecat(user, receipt_token, product_id):
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
