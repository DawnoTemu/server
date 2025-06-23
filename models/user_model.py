from datetime import datetime, timedelta
import jwt
import uuid
from werkzeug.security import generate_password_hash, check_password_hash
from flask import current_app
from database import db

class User(db.Model):
    """User account model for authentication and profile management"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    email_confirmed = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=False)
    last_login = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<User {self.email}>"
    
    def set_password(self, password):
        """Set the password hash from a plaintext password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check if the plaintext password matches the stored hash"""
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        """Convert user to dictionary (for API responses)"""
        return {
            'id': self.id,
            'email': self.email,
            'email_confirmed': self.email_confirmed,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }
    
    def get_confirmation_token(self, expires_in=86400):
        """Generate email confirmation token valid for 24 hours"""
        return self._generate_token(
            {'confirm': self.id, 'type': 'confirm'}, 
            expires_in
        )
    
    def get_reset_password_token(self, expires_in=3600):
        """Generate password reset token valid for 1 hour"""
        return self._generate_token(
            {'reset_password': self.id, 'type': 'reset_password'}, 
            expires_in
        )
    
    def _generate_token(self, payload, expires_in):
        """Generate a JWT token with the given payload"""
        payload.update({
            'exp': datetime.utcnow() + timedelta(seconds=expires_in),
            'iat': datetime.utcnow(),
            'jti': str(uuid.uuid4())
        })
        return jwt.encode(
            payload,
            current_app.config['SECRET_KEY'],
            algorithm='HS256'
        )
    
    @staticmethod
    def verify_token(token, token_type):
        """Verify a token and return the user ID if valid"""
        try:
            payload = jwt.decode(
                token, 
                current_app.config['SECRET_KEY'],
                algorithms=['HS256']
            )
            
            # Check token type
            if payload.get('type') != token_type:
                return None
                
            # Return user ID based on token type
            if token_type == 'confirm':
                return payload.get('confirm')
            elif token_type == 'reset_password':
                return payload.get('reset_password')
                
            return None
        except:
            return None


class UserModel:
    """Data access layer for User model"""
    
    @staticmethod
    def get_by_id(user_id):
        """Get user by ID"""
        return User.query.get(user_id)
    
    @staticmethod
    def get_by_email(email):
        """Get user by email"""
        return User.query.filter_by(email=email).first()
    
    @staticmethod
    def create_user(email, password):
        """
        Create a new user
        
        Args:
            email: User's email address
            password: Plaintext password (will be hashed)
            
        Returns:
            User: Newly created user object
        """
        user = User(email=email)
        user.set_password(password)
        
        # Add to database
        db.session.add(user)
        db.session.commit()
        
        return user
    
    @staticmethod
    def confirm_email(user_id):
        """
        Mark user's email as confirmed
        
        Args:
            user_id: ID of the user
            
        Returns:
            bool: True if successful, False otherwise
        """
        user = UserModel.get_by_id(user_id)
        if not user:
            return False
            
        user.email_confirmed = True
        db.session.commit()
        return True
    
    @staticmethod
    def update_password(user_id, new_password):
        """
        Update user's password
        
        Args:
            user_id: ID of the user
            new_password: New plaintext password
            
        Returns:
            bool: True if successful, False otherwise
        """
        user = UserModel.get_by_id(user_id)
        if not user:
            return False
            
        user.set_password(new_password)
        db.session.commit()
        return True
    
    @staticmethod
    def update_last_login(user_id):
        """Update user's last login timestamp"""
        user = UserModel.get_by_id(user_id)
        if user:
            user.last_login = datetime.utcnow()
            db.session.commit()
    
    @staticmethod
    def activate_user(user_id):
        """
        Activate a user account
        
        Args:
            user_id: ID of the user
            
        Returns:
            bool: True if successful, False otherwise
        """
        user = UserModel.get_by_id(user_id)
        if not user:
            return False
            
        user.is_active = True
        db.session.commit()
        return True
    
    @staticmethod
    def deactivate_user(user_id):
        """
        Deactivate a user account
        
        Args:
            user_id: ID of the user
            
        Returns:
            bool: True if successful, False otherwise
        """
        user = UserModel.get_by_id(user_id)
        if not user:
            return False
            
        user.is_active = False
        db.session.commit()
        return True
    
    @staticmethod
    def get_all_users():
        """
        Get all users (for admin purposes)
        
        Returns:
            list: List of all User objects
        """
        return User.query.all()
    
    @staticmethod
    def get_pending_users():
        """
        Get all inactive users (for admin approval)
        
        Returns:
            list: List of inactive User objects
        """
        return User.query.filter_by(is_active=False).all()
