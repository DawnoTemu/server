from datetime import datetime, timedelta
import jwt
from flask import current_app
from models.user_model import UserModel, User
from utils.email_service import EmailService
from database import db

class AuthController:
    """Controller for authentication-related operations"""
    
    @staticmethod
    def register(email, password, password_confirm):
        """
        Register a new user
        
        Args:
            email: User's email
            password: Plaintext password
            password_confirm: Password confirmation
            
        Returns:
            tuple: (success, data/error message, status_code)
        """
        # Check if passwords match
        if password != password_confirm:
            return False, {"error": "Passwords do not match"}, 400
            
        # Check if email already exists
        if UserModel.get_by_email(email):
            return False, {"error": "Email already registered"}, 409
            
        try:
            # Create the user
            user = UserModel.create_user(email, password)
            
            # Generate confirmation token
            token = user.get_confirmation_token()
            
            # Send confirmation email
            EmailService.send_confirmation_email(email, token)
            
            return True, {"message": "Registration successful. Please check your email to confirm your account."}, 201
            
        except Exception as e:
            db.session.rollback()
            return False, {"error": str(e)}, 500
    
    @staticmethod
    def login(email, password):
        """
        Authenticate a user and generate JWT tokens
        
        Args:
            email: User's email
            password: Plaintext password
            
        Returns:
            tuple: (success, data/error message, status_code)
        """
        # Get user by email
        user = UserModel.get_by_email(email)
        
        if not user or not user.check_password(password):
            return False, {"error": "Invalid email or password"}, 401
            
        if not user.is_active:
            return False, {"error": "Account is deactivated. Please contact support."}, 403
            
        # Update last login time
        UserModel.update_last_login(user.id)
        
        # Generate tokens
        access_token = AuthController.generate_access_token(user)
        refresh_token = AuthController.generate_refresh_token(user)
        
        return True, {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": user.to_dict()
        }, 200
    
    @staticmethod
    def refresh_token(refresh_token):
        """
        Generate a new access token using a refresh token
        
        Args:
            refresh_token: Valid refresh token
            
        Returns:
            tuple: (success, data/error message, status_code)
        """
        try:
            # Decode and verify the refresh token
            payload = jwt.decode(
                refresh_token,
                current_app.config['SECRET_KEY'],
                algorithms=['HS256']
            )
            
            # Check token type
            if payload.get('type') != 'refresh':
                return False, {"error": "Invalid token type"}, 401
                
            # Get user
            user_id = payload.get('sub')
            user = UserModel.get_by_id(user_id)
            
            if not user or not user.is_active:
                return False, {"error": "Invalid or inactive user"}, 401
                
            # Generate new access token
            access_token = AuthController.generate_access_token(user)
            
            return True, {"access_token": access_token}, 200
            
        except jwt.ExpiredSignatureError:
            return False, {"error": "Refresh token has expired. Please log in again."}, 401
        except jwt.InvalidTokenError:
            return False, {"error": "Invalid token. Please log in again."}, 401
        except Exception as e:
            return False, {"error": str(e)}, 500
    
    @staticmethod
    def confirm_email(token):
        """
        Confirm a user's email address
        
        Args:
            token: Email confirmation token
            
        Returns:
            tuple: (success, message, status_code)
        """
        # Verify token and get user ID
        user_id = User.verify_token(token, 'confirm')
        
        if not user_id:
            return False, {"error": "Invalid or expired confirmation link"}, 400
            
        # Confirm the email
        if UserModel.confirm_email(user_id):
            return True, {"message": "Email confirmed successfully. You can now log in."}, 200
        else:
            return False, {"error": "User not found"}, 404
    
    @staticmethod
    def request_password_reset(email):
        """
        Request a password reset for a user
        
        Args:
            email: User's email address
            
        Returns:
            tuple: (success, message, status_code)
        """
        user = UserModel.get_by_email(email)
        
        # Always return success to prevent email enumeration
        if not user:
            return True, {"message": "If an account with that email exists, a password reset link has been sent."}, 200
            
        # Generate reset token
        token = user.get_reset_password_token()
        
        # Send reset email
        EmailService.send_password_reset_email(email, token)
        
        return True, {"message": "Password reset link has been sent to your email."}, 200
    
    @staticmethod
    def reset_password(token, new_password, new_password_confirm):
        """
        Reset a user's password using a reset token
        
        Args:
            token: Password reset token
            new_password: New plaintext password
            new_password_confirm: Password confirmation
            
        Returns:
            tuple: (success, message, status_code)
        """
        # Check if passwords match
        if new_password != new_password_confirm:
            return False, {"error": "Passwords do not match"}, 400
            
        # Verify token and get user ID
        user_id = User.verify_token(token, 'reset_password')
        
        if not user_id:
            return False, {"error": "Invalid or expired reset link"}, 400
            
        # Update the password
        if UserModel.update_password(user_id, new_password):
            return True, {"message": "Password has been reset successfully. You can now log in with your new password."}, 200
        else:
            return False, {"error": "User not found"}, 404
    
    @staticmethod
    def generate_access_token(user, expires_delta=timedelta(minutes=15)):
        """
        Generate a JWT access token for a user
        
        Args:
            user: User object
            expires_delta: Token expiration time (default: 15 minutes)
            
        Returns:
            str: JWT access token
        """
        now = datetime.utcnow()
        payload = {
            'sub': user.id,
            'email': user.email,
            'type': 'access',
            'iat': now,
            'exp': now + expires_delta
        }
        
        return jwt.encode(
            payload,
            current_app.config['SECRET_KEY'],
            algorithm='HS256'
        )
    
    @staticmethod
    def generate_refresh_token(user, expires_delta=timedelta(days=7)):
        """
        Generate a JWT refresh token for a user
        
        Args:
            user: User object
            expires_delta: Token expiration time (default: 7 days)
            
        Returns:
            str: JWT refresh token
        """
        now = datetime.utcnow()
        payload = {
            'sub': user.id,
            'type': 'refresh',
            'iat': now,
            'exp': now + expires_delta
        }
        
        return jwt.encode(
            payload,
            current_app.config['SECRET_KEY'],
            algorithm='HS256'
        )