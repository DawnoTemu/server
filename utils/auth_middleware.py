from functools import wraps
from datetime import datetime, timezone
import jwt
import os
from flask import request, jsonify, current_app
from models.user_model import UserModel

def token_required(f):
    """
    Decorator for routes that require a valid JWT token
    
    Usage:
        @app.route('/some-protected-route')
        @token_required
        def protected_route(current_user):
            # Function receives the current authenticated user
            return jsonify({"message": f"Hello, {current_user.email}!"})
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Get token from header
        auth_header = request.headers.get('Authorization')
        
        if auth_header:
            # Check if it's a Bearer token
            parts = auth_header.split()
            if len(parts) == 2 and parts[0].lower() == 'bearer':
                token = parts[1]
        
        if not token:
            return jsonify({"error": "Authentication token is missing"}), 401
        
        try:
            # Decode token
            payload = jwt.decode(
                token, 
                current_app.config['SECRET_KEY'],
                algorithms=['HS256']
            )
            
            # Verify it's an access token
            if payload.get('type') != 'access':
                return jsonify({"error": "Invalid token type"}), 401
            
            # Get current user
            current_user = UserModel.get_by_id(payload['sub'])
            
            if not current_user:
                return jsonify({"error": "User not found"}), 401
                
            if not current_user.is_active:
                return jsonify({"error": "User account is inactive"}), 403

            token_iat = payload.get("iat")
            if token_iat:
                issued_at = datetime.fromtimestamp(token_iat, tz=timezone.utc)
                updated_at = current_user.updated_at
                if updated_at:
                    updated_at = updated_at.replace(tzinfo=timezone.utc)
                    # Invalidate tokens issued before the last profile change/deactivation
                    if issued_at < updated_at:
                        return jsonify({"error": "Token is no longer valid, please log in again"}), 401
                
            # Check if email is confirmed
            if not current_user.email_confirmed:
                return jsonify({"error": "Please confirm your email address before accessing this resource"}), 403
                
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        
        # Add current_user to function arguments
        return f(current_user, *args, **kwargs)
        
    return decorated

def admin_required(f):
    """
    Decorator for routes that require admin privileges
    
    Usage:
        @app.route('/admin/some-route')
        @admin_required
        def admin_route(current_user):
            # Function receives the current authenticated admin user
            return jsonify({"message": f"Hello admin, {current_user.email}!"})
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Get token from header
        auth_header = request.headers.get('Authorization')
        
        if auth_header:
            # Check if it's a Bearer token
            parts = auth_header.split()
            if len(parts) == 2 and parts[0].lower() == 'bearer':
                token = parts[1]
        
        if not token:
            return jsonify({"error": "Admin authentication token is missing"}), 401
        
        try:
            # Decode token
            payload = jwt.decode(
                token, 
                current_app.config['SECRET_KEY'],
                algorithms=['HS256']
            )
            
            # Verify it's an admin access token
            if payload.get('type') not in ['access', 'admin_access']:
                return jsonify({"error": "Invalid token type for admin access"}), 401
            
            # Get current user
            current_user = UserModel.get_by_id(payload['sub'])
            
            if not current_user:
                return jsonify({"error": "User not found"}), 401
                
            if not current_user.is_active:
                return jsonify({"error": "User account is inactive"}), 403

            token_iat = payload.get("iat")
            if token_iat:
                issued_at = datetime.fromtimestamp(token_iat, tz=timezone.utc)
                updated_at = current_user.updated_at
                if updated_at:
                    updated_at = updated_at.replace(tzinfo=timezone.utc)
                    if issued_at < updated_at:
                        return jsonify({"error": "Token is no longer valid, please log in again"}), 401
                
            # Check if email is confirmed
            if not current_user.email_confirmed:
                return jsonify({"error": "Please confirm your email address before accessing admin resources"}), 403
            
            # Critical: Check if user has admin privileges
            if not current_user.is_admin:
                return jsonify({
                    "error": "Access denied. Admin privileges required.",
                    "message": "This endpoint requires administrator access."
                }), 403
                
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Admin token has expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid admin token"}), 401
        
        # Add current_user to function arguments
        return f(current_user, *args, **kwargs)
        
    return decorated

def api_key_required(f):
    """
    Decorator for routes that require API key authentication (for production operations)
    
    Usage:
        @app.route('/admin/production-operation')
        @api_key_required
        def production_route():
            return jsonify({"message": "Authenticated via API key"})
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = None
        
        # Get API key from header
        api_key = request.headers.get('X-API-Key')
        
        if not api_key:
            # Also check Authorization header for API key format
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('ApiKey '):
                api_key = auth_header[7:]  # Remove 'ApiKey ' prefix
        
        if not api_key:
            return jsonify({"error": "API key is required"}), 401
        
        # Directly read from environment variables for robustness, bypassing app config.
        admin_keys_str = os.getenv('ADMIN_API_KEYS', '')
        valid_api_keys = [key.strip() for key in admin_keys_str.split(',')] if admin_keys_str else []
        
        if not valid_api_keys or api_key not in valid_api_keys:
            return jsonify({"error": "Invalid API key"}), 401
        
        return f(*args, **kwargs)
        
    return decorated
