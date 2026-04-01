import logging

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


class AddonController:

    @staticmethod
    def grant_addon(user, receipt_token, product_id, platform):
        if not receipt_token or not product_id or not platform:
            return False, {"error": "Missing required fields"}, 400

        if product_id not in ADDON_PRODUCTS:
            return False, {"error": f"Unknown product: {product_id}"}, 400

        if platform not in VALID_PLATFORMS:
            return False, {"error": f"Invalid platform: {platform}"}, 400

        if not user.subscription_active:
            return False, {"error": "Active subscription required"}, 403

        # Idempotency check
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

        credits_amount = ADDON_PRODUCTS[product_id]

        try:
            credit_grant(
                user_id=user.id,
                amount=credits_amount,
                reason=f"addon:{product_id}",
                source="add_on",
                expires_at=None,
            )

            tx = ConsumedAddonTransaction(
                receipt_token=receipt_token,
                user_id=user.id,
                product_id=product_id,
                platform=platform,
                credits_granted=credits_amount,
            )
            db.session.add(tx)
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            logger.error("Addon grant failed for user %s: %s", user.id, exc)
            return False, {"error": "Failed to grant credits"}, 500

        # Re-read balance after grant
        db.session.refresh(user)

        return True, {
            "credits_granted": credits_amount,
            "new_balance": user.credits_balance,
        }, 200
