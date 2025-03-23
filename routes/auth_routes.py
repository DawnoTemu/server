from flask import request, jsonify
from controllers.auth_controller import AuthController
from utils.auth_middleware import token_required
from routes import auth_bp

# POST /auth/register - Register a new user
@auth_bp.route('/register', methods=['POST'])
def register():
    """Register a new user account"""
    data = request.json
    
    # Required fields
    email = data.get('email')
    password = data.get('password')
    password_confirm = data.get('password_confirm')
    
    # Validate required fields
    if not all([email, password, password_confirm]):
        return jsonify({"error": "Email, password, and password confirmation are required"}), 400
    
    # Register the user
    success, result, status_code = AuthController.register(
        email, 
        password, 
        password_confirm
    )
    
    return jsonify(result), status_code

# POST /auth/login - Authenticate user
@auth_bp.route('/login', methods=['POST'])
def login():
    """Log in a user and return authentication tokens"""
    data = request.json
    
    # Required fields
    email = data.get('email')
    password = data.get('password')
    
    # Validate required fields
    if not all([email, password]):
        return jsonify({"error": "Email and password are required"}), 400
    
    # Authenticate the user
    success, result, status_code = AuthController.login(email, password)
    
    return jsonify(result), status_code

# POST /auth/refresh - Refresh access token
@auth_bp.route('/refresh', methods=['POST'])
def refresh_token():
    """Generate a new access token using a refresh token"""
    data = request.json
    
    # Required fields
    refresh_token = data.get('refresh_token')
    
    # Validate required fields
    if not refresh_token:
        return jsonify({"error": "Refresh token is required"}), 400
    
    # Refresh the token
    success, result, status_code = AuthController.refresh_token(refresh_token)
    
    return jsonify(result), status_code

# GET /auth/me - Get current user
@auth_bp.route('/me', methods=['GET'])
@token_required
def get_current_user(current_user):
    """Get the authenticated user's profile information"""
    return jsonify(current_user.to_dict()), 200

# GET /auth/confirm-email/:token - Confirm email
@auth_bp.route('/confirm-email/<token>', methods=['GET'])
def confirm_email(token):
    """Confirm a user's email address using a token"""
    success, result, status_code = AuthController.confirm_email(token)
    
    return jsonify(result), status_code

# POST /auth/reset-password-request - Request password reset
@auth_bp.route('/reset-password-request', methods=['POST'])
def reset_password_request():
    """Request a password reset email"""
    data = request.json
    
    # Required fields
    email = data.get('email')
    
    # Validate required fields
    if not email:
        return jsonify({"error": "Email is required"}), 400
    
    # Request password reset
    success, result, status_code = AuthController.request_password_reset(email)
    
    return jsonify(result), status_code

# POST /auth/reset-password/:token - Reset password
@auth_bp.route('/reset-password/<token>', methods=['POST'])
def reset_password(token):
    """Reset a user's password using a token"""
    data = request.json
    
    # Required fields
    new_password = data.get('new_password')
    new_password_confirm = data.get('new_password_confirm')
    
    # Validate required fields
    if not all([new_password, new_password_confirm]):
        return jsonify({"error": "New password and confirmation are required"}), 400
    
    # Reset the password
    success, result, status_code = AuthController.reset_password(
        token,
        new_password,
        new_password_confirm
    )
    
    return jsonify(result), status_code