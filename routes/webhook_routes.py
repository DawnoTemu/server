import hmac
import logging
import os

from flask import jsonify, request
from werkzeug.exceptions import BadRequest

from config import Config
from routes import webhook_bp
from controllers.subscription_controller import SubscriptionController
from utils.rate_limiter import limiter

logger = logging.getLogger(__name__)


@webhook_bp.route('/api/webhooks/revenuecat', methods=['POST'])
@limiter.limit("60 per minute")
def revenuecat_webhook():
    secret = Config.REVENUECAT_WEBHOOK_SECRET or os.getenv("REVENUECAT_WEBHOOK_SECRET")
    if not secret:
        logger.error("REVENUECAT_WEBHOOK_SECRET not configured — rejecting webhook")
        return jsonify({"error": "Unauthorized"}), 401

    auth = request.headers.get('Authorization', '')
    # Strip optional Bearer prefix so the comparison works regardless of
    # whether RevenueCat sends "Bearer <secret>" or just "<secret>".
    token = auth.removeprefix('Bearer ').strip() if auth else ''
    if not token or not hmac.compare_digest(token, secret):
        logger.warning("Webhook auth failed from %s", request.remote_addr)
        return jsonify({"error": "Unauthorized"}), 401

    try:
        payload = request.get_json(force=False, silent=False)
    except BadRequest as exc:
        logger.warning("Malformed webhook JSON: %s", exc)
        return jsonify({"error": "Invalid JSON payload"}), 400

    if not payload:
        return jsonify({"error": "Invalid payload"}), 400

    try:
        success, data, status = SubscriptionController.handle_revenuecat_webhook(payload)
        return jsonify(data), status
    except Exception as exc:
        logger.error("Unhandled webhook error: %s", exc, exc_info=True)
        return jsonify({"error": "Internal error"}), 500
