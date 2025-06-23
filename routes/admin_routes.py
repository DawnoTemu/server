from flask import request, jsonify
from models.user_model import UserModel
from utils.auth_middleware import token_required
from routes import admin_bp

# GET /admin/users - List all users (admin only)
@admin_bp.route('/users', methods=['GET'])
@token_required
def list_users(current_user):
    """List all users (admin only)"""
    # TODO: Add admin role check when admin system is implemented
    # For now, this is a simple implementation
    
    users = UserModel.get_all_users()
    return jsonify({
        "users": [user.to_dict() for user in users]
    }), 200

# GET /admin/users/pending - List pending (inactive) users
@admin_bp.route('/users/pending', methods=['GET'])
@token_required
def list_pending_users(current_user):
    """List all pending (inactive) users for approval"""
    # TODO: Add admin role check when admin system is implemented
    
    pending_users = UserModel.get_pending_users()
    return jsonify({
        "pending_users": [user.to_dict() for user in pending_users]
    }), 200

# POST /admin/users/<user_id>/activate - Activate a user
@admin_bp.route('/users/<int:user_id>/activate', methods=['POST'])
@token_required
def activate_user(current_user, user_id):
    """Activate a user account (admin only)"""
    # TODO: Add admin role check when admin system is implemented
    
    success = UserModel.activate_user(user_id)
    
    if success:
        return jsonify({
            "message": "User activated successfully"
        }), 200
    else:
        return jsonify({
            "error": "User not found or could not be activated"
        }), 404

# POST /admin/users/<user_id>/deactivate - Deactivate a user
@admin_bp.route('/users/<int:user_id>/deactivate', methods=['POST'])
@token_required
def deactivate_user(current_user, user_id):
    """Deactivate a user account (admin only)"""
    # TODO: Add admin role check when admin system is implemented
    
    success = UserModel.deactivate_user(user_id)
    
    if success:
        return jsonify({
            "message": "User deactivated successfully"
        }), 200
    else:
        return jsonify({
            "error": "User not found or could not be deactivated"
        }), 404

# GET /admin/users/<user_id> - Get user details
@admin_bp.route('/users/<int:user_id>', methods=['GET'])
@token_required
def get_user(current_user, user_id):
    """Get detailed information about a specific user (admin only)"""
    # TODO: Add admin role check when admin system is implemented
    
    user = UserModel.get_by_id(user_id)
    
    if user:
        return jsonify(user.to_dict()), 200
    else:
        return jsonify({
            "error": "User not found"
        }), 404 