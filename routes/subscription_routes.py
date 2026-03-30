from flask import jsonify, request

from routes import subscription_bp
from controllers.subscription_controller import SubscriptionController
from utils.auth_middleware import token_required
from utils.rate_limiter import limiter


@subscription_bp.route('/api/user/subscription-status', methods=['GET'])
@token_required
@limiter.limit("30 per minute")
def get_subscription_status(current_user):
    success, data, status = SubscriptionController.get_subscription_status(current_user)
    return jsonify(data), status


@subscription_bp.route('/api/user/link-revenuecat', methods=['POST'])
@token_required
@limiter.limit("5 per minute")
def link_revenuecat(current_user):
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid request body"}), 400

    revenuecat_id = (data.get("revenuecat_app_user_id") or "").strip()
    success, result, status = SubscriptionController.link_revenuecat(current_user, revenuecat_id)
    return jsonify(result), status
