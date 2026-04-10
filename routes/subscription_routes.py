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
    # The RC app_user_id is authoritatively derived from the authenticated
    # user's server-side id inside the controller. Client input is only used
    # as a sanity check (must match) so we accept empty / missing bodies.
    data = request.get_json(silent=True) or {}
    revenuecat_id = data.get("revenuecat_app_user_id")
    success, result, status = SubscriptionController.link_revenuecat(current_user, revenuecat_id)
    return jsonify(result), status
