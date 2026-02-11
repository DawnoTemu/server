from flask import request, jsonify, render_template
from controllers.auth_controller import AuthController
from controllers.user_controller import UserController
from utils.auth_middleware import token_required
from utils.rate_limiter import rate_limit
from utils.validators import is_valid_email, validate_password
from routes import auth_bp

# POST /auth/register - Register a new user
@auth_bp.route('/register', methods=['POST'])
@rate_limit(limit=5, window_seconds=60)
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
@rate_limit(limit=10, window_seconds=60)
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
@rate_limit(limit=20, window_seconds=60)
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


# PATCH /auth/me - Update current user profile
@auth_bp.route('/me', methods=['PATCH'])
@token_required
@rate_limit(limit=5, window_seconds=60)
def update_current_user(current_user):
    """Update the authenticated user's profile information"""
    data = request.get_json(silent=True) or request.form or {}

    new_email = data.get('email')
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    new_password_confirm = data.get('new_password_confirm')

    if new_email and not is_valid_email(new_email):
        return jsonify({"error": "Invalid email format"}), 400
    if new_password and not validate_password(new_password):
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    success, result, status_code = UserController.update_profile(
        current_user,
        current_password=current_password,
        new_email=new_email,
        new_password=new_password,
        new_password_confirm=new_password_confirm,
    )

    return jsonify(result), status_code


# DELETE /auth/me - Delete current user account
@auth_bp.route('/me', methods=['DELETE'])
@token_required
@rate_limit(limit=3, window_seconds=300)
def delete_current_user(current_user):
    """Delete the authenticated user's account"""
    data = request.get_json(silent=True) or {}
    current_password = data.get('current_password')

    success, result, status_code = UserController.delete_account(
        current_user,
        current_password=current_password,
    )

    return jsonify(result), status_code

# GET /auth/confirm-email/:token - Confirm email
@auth_bp.route('/confirm-email/<token>', methods=['GET'])
def confirm_email(token):
    """Confirm a user's email address using a token"""
    success, result, status_code = AuthController.confirm_email(token)
    
    if success:
        return render_template('auth/email_confirmed.html')
    else:
        error_message = result.get('error', 'Wystąpił nieznany błąd.')
        return render_template('auth/email_confirmation_error.html', error_message=error_message), status_code

# POST /auth/resend-confirmation - Resend confirmation email
@auth_bp.route('/resend-confirmation', methods=['POST'])
@rate_limit(limit=5, window_seconds=300)
def resend_confirmation():
    """Resend the email confirmation link"""
    data = request.json
    
    # Required fields
    email = data.get('email')
    
    # Validate required fields
    if not email:
        return jsonify({"error": "Email is required"}), 400
    
    # Resend confirmation email
    success, result, status_code = AuthController.resend_confirmation_email(email)
    
    return jsonify(result), status_code

# POST /auth/reset-password-request - Request password reset
@auth_bp.route('/reset-password-request', methods=['POST'])
@rate_limit(limit=5, window_seconds=300)
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

# GET/POST /auth/reset-password/:token - Reset password
@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
@rate_limit(limit=5, window_seconds=300)
def reset_password(token):
    """Reset a user's password using a token."""
    if request.method == "GET":
        # Render a simple HTML form so email links work in browsers
        return render_template("auth/reset_password.html", token=token, success=False, error=None)

    # Accept JSON or form payloads without requiring application/json
    if request.is_json:
        data = request.get_json(silent=True) or {}
    else:
        data = request.form.to_dict() if request.form else {}

    new_password = data.get("new_password")
    new_password_confirm = data.get("new_password_confirm")

    if not all([new_password, new_password_confirm]):
        if request.is_json:
            return jsonify({"error": "New password and confirmation are required"}), 400
        return render_template(
            "auth/reset_password.html",
            token=token,
            success=False,
            error="Nowe hasło i potwierdzenie są wymagane.",
        ), 400

    success, result, status_code = AuthController.reset_password(
        token, new_password, new_password_confirm
    )
    if request.is_json:
        return jsonify(result), status_code

    if success:
        return render_template(
            "auth/reset_password.html",
            token=None,
            success=True,
            message="Hasło zostało zresetowane. Możesz się teraz zalogować.",
            error=None,
        ), status_code

    return render_template(
        "auth/reset_password.html",
        token=token,
        success=False,
        error=result.get("error") if isinstance(result, dict) else "Reset hasła nie powiódł się.",
    ), status_code
