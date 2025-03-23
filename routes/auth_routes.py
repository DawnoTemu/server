from flask import request, jsonify, Blueprint
from controllers.auth_controller import AuthController
from utils.auth_middleware import token_required
from routes import auth_bp

@auth_bp.route('/register', methods=['POST'])
def register():
    """API endpoint for user registration"""
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

@auth_bp.route('/login', methods=['POST'])
def login():
    """API endpoint for user login"""
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

@auth_bp.route('/refresh', methods=['POST'])
def refresh_token():
    """API endpoint to refresh access token"""
    data = request.json
    
    # Required fields
    refresh_token = data.get('refresh_token')
    
    # Validate required fields
    if not refresh_token:
        return jsonify({"error": "Refresh token is required"}), 400
    
    # Refresh the token
    success, result, status_code = AuthController.refresh_token(refresh_token)
    
    return jsonify(result), status_code

@auth_bp.route('/me', methods=['GET'])
@token_required
def me(current_user):
    """API endpoint to get current user information"""
    return jsonify(current_user.to_dict()), 200

@auth_bp.route('/confirm-email/<token>', methods=['GET'])
def confirm_email(token):
    """API endpoint to confirm email address"""
    success, result, status_code = AuthController.confirm_email(token)
    
    return jsonify(result), status_code

@auth_bp.route('/reset-password-request', methods=['POST'])
def reset_password_request():
    """API endpoint to request password reset"""
    data = request.json
    
    # Required fields
    email = data.get('email')
    
    # Validate required fields
    if not email:
        return jsonify({"error": "Email is required"}), 400
    
    # Request password reset
    success, result, status_code = AuthController.request_password_reset(email)
    
    return jsonify(result), status_code

@auth_bp.route('/reset-password/<token>', methods=['POST'])
def reset_password(token):
    """API endpoint to reset password"""
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