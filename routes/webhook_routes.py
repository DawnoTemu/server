import hmac
import logging
import os

from flask import jsonify, request

from routes import webhook_bp
from controllers.subscription_controller import SubscriptionController

logger = logging.getLogger(__name__)


@webhook_bp.route('/api/webhooks/revenuecat', methods=['POST'])
def revenuecat_webhook():
    secret = os.getenv("REVENUECAT_WEBHOOK_SECRET")
    if not secret:
        logger.error("REVENUECAT_WEBHOOK_SECRET not configured")
        return jsonify({"error": "Webhook not configured"}), 500

    auth = request.headers.get('Authorization', '')
    if not hmac.compare_digest(auth, secret):
        return jsonify({"error": "Unauthorized"}), 401

    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "Invalid payload"}), 400

    success, data, status = SubscriptionController.handle_revenuecat_webhook(payload)
    return jsonify(data), status
