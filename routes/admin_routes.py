from flask import request, jsonify
from models.user_model import UserModel
from controllers.admin_controller import AdminController
from utils.auth_middleware import admin_required, api_key_required
from routes import admin_bp

# GET /admin/users - List all users (admin only)
@admin_bp.route('/users', methods=['GET'])
@admin_required
def list_users(current_user):
    """List all users (admin only)"""
    users = UserModel.get_all_users()
    return jsonify({
        "users": [user.to_dict() for user in users]
    }), 200

# GET /admin/users/pending - List pending (inactive) users
@admin_bp.route('/users/pending', methods=['GET'])
@admin_required
def list_pending_users(current_user):
    """List all pending (inactive) users for approval"""
    pending_users = UserModel.get_pending_users()
    return jsonify({
        "pending_users": [user.to_dict() for user in pending_users]
    }), 200

# POST /admin/users/<user_id>/activate - Activate a user
@admin_bp.route('/users/<int:user_id>/activate', methods=['POST'])
@admin_required
def activate_user(current_user, user_id):
    """Activate a user account (admin only)"""
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
@admin_required
def deactivate_user(current_user, user_id):
    """Deactivate a user account (admin only)"""
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
@admin_required
def get_user(current_user, user_id):
    """Get detailed information about a specific user (admin only)"""
    user = UserModel.get_by_id(user_id)
    
    if user:
        return jsonify(user.to_dict()), 200
    else:
        return jsonify({
            "error": "User not found"
        }), 404

# POST /admin/stories/upload - Upload a single story (SECURE: Use API key for production)
@admin_bp.route('/stories/upload', methods=['POST'])
@api_key_required
def upload_story():
    """Upload a single story to the database (production: API key required)"""
    if not request.is_json:
        return jsonify({
            "error": "Content-Type must be application/json"
        }), 400
    
    story_data = request.get_json()
    
    if not story_data:
        return jsonify({
            "error": "No story data provided"
        }), 400
    
    success, result, status_code = AdminController.upload_story(story_data)
    return jsonify(result), status_code

# POST /admin/stories/bulk-upload - Upload multiple stories (SECURE: Use API key for production)
@admin_bp.route('/stories/bulk-upload', methods=['POST'])
@api_key_required
def bulk_upload_stories():
    """Upload multiple stories to the database (production: API key required)"""
    if not request.is_json:
        return jsonify({
            "error": "Content-Type must be application/json"
        }), 400
    
    data = request.get_json()
    
    if not data or 'stories' not in data:
        return jsonify({
            "error": "No stories data provided. Expected format: {'stories': [...]}"
        }), 400
    
    stories_data = data['stories']
    
    if not isinstance(stories_data, list):
        return jsonify({
            "error": "Stories must be provided as a list"
        }), 400
    
    success, result, status_code = AdminController.bulk_upload_stories(stories_data)
    return jsonify(result), status_code

# POST /admin/stories/upload-with-image - Upload story with image (SECURE: Use API key for production)
@admin_bp.route('/stories/upload-with-image', methods=['POST'])
@api_key_required
def upload_story_with_image():
    """Upload a story with optional image download and S3 upload (production: API key required)"""
    if not request.is_json:
        return jsonify({
            "error": "Content-Type must be application/json"
        }), 400
    
    data = request.get_json()
    
    if not data or 'story' not in data:
        return jsonify({
            "error": "No story data provided. Expected format: {'story': {...}, 'image_url': '...'}"
        }), 400
    
    story_data = data['story']
    image_url = data.get('image_url')
    
    success, result, status_code = AdminController.upload_story_with_image(story_data, image_url)
    return jsonify(result), status_code

# GET /admin/stories/stats - Get stories statistics
@admin_bp.route('/stories/stats', methods=['GET'])
@admin_required
def get_stories_stats(current_user):
    """Get statistics about stories in the database (admin only)"""
    success, result, status_code = AdminController.get_stories_stats()
    return jsonify(result), status_code

# POST /admin/users/<user_id>/promote - Promote user to admin
@admin_bp.route('/users/<int:user_id>/promote', methods=['POST'])
@admin_required
def promote_user_to_admin(current_user, user_id):
    """Promote a user to admin status (super admin only)"""
    success = UserModel.promote_to_admin(user_id)
    
    if success:
        return jsonify({
            "message": "User promoted to admin successfully"
        }), 200
    else:
        return jsonify({
            "error": "User not found or could not be promoted"
        }), 404

# POST /admin/users/<user_id>/revoke-admin - Revoke admin privileges
@admin_bp.route('/users/<int:user_id>/revoke-admin', methods=['POST'])
@admin_required
def revoke_admin_privileges(current_user, user_id):
    """Revoke admin privileges from a user (super admin only)"""
    # Prevent self-demotion
    if current_user.id == user_id:
        return jsonify({
            "error": "Cannot revoke your own admin privileges"
        }), 403
    
    success = UserModel.revoke_admin(user_id)
    
    if success:
        return jsonify({
            "message": "Admin privileges revoked successfully"
        }), 200
    else:
        return jsonify({
            "error": "User not found or could not revoke admin privileges"
        }), 404

# POST /admin/auth/generate-token - Generate admin token for API access
@admin_bp.route('/auth/generate-token', methods=['POST'])
@admin_required
def generate_admin_token(current_user):
    """Generate an admin token for API access (admin only)"""
    data = request.get_json() if request.is_json else {}
    expires_in = data.get('expires_in', 3600)  # Default 1 hour
    
    # Limit maximum expiration time
    max_expires = 24 * 3600  # 24 hours max
    if expires_in > max_expires:
        expires_in = max_expires
    
    admin_token = current_user.get_admin_token(expires_in)
    
    if not admin_token:
        return jsonify({
            "error": "Failed to generate admin token. User may not have admin privileges."
        }), 403
    
    return jsonify({
        "admin_token": admin_token,
        "expires_in": expires_in,
        "token_type": "admin_access",
        "message": f"Admin token generated successfully. Expires in {expires_in} seconds."
    }), 200 