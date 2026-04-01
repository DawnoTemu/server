from flask import jsonify

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
