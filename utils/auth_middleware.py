from functools import wraps
import jwt
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
                
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        
        # Add current_user to function arguments
        return f(current_user, *args, **kwargs)
        
    return decorated

# Note: Admin access is managed separately through the Flask-Admin interface with password protection.
# This middleware is left here for potential future use but is not currently connected to the User model.