import os
import uuid
import mimetypes
from functools import wraps
from datetime import datetime, timedelta

from flask import redirect, url_for, request, flash, session
from flask_admin import Admin, AdminIndexView, expose
from flask_admin.contrib.sqla import ModelView
from flask import flash, redirect, url_for
from werkzeug.security import generate_password_hash
from models.user_model import User
from flask_admin.form import FileUploadField
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash

from database import db
from models.story_model import Story
from models.user_model import User
from config import Config

# Constants
DEFAULT_SESSION_TIMEOUT = 3600  # 1 hour in seconds
MAX_LOGIN_ATTEMPTS = 5
LOGIN_COOLDOWN = 300  # 5 minutes in seconds
ALLOWED_EXTENSIONS = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg']
S3_COVERS_PREFIX = "covers/"

# Get admin password from environment with no default
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')
if not ADMIN_PASSWORD:
    raise ValueError("ADMIN_PASSWORD environment variable must be set")

# Optional support for hashed password
ADMIN_PASSWORD_HASH = os.getenv('ADMIN_PASSWORD_HASH')

# Store login attempts
login_attempts = {}


def is_authenticated():
    """Check if the current session is authenticated and not expired."""
    if not session.get('admin_authenticated', False):
        return False
    
    # Check session expiration
    last_activity = session.get('last_activity')
    if not last_activity or (datetime.utcnow() - datetime.fromisoformat(last_activity) > 
                            timedelta(seconds=int(os.getenv('SESSION_TIMEOUT', DEFAULT_SESSION_TIMEOUT)))):
        session.pop('admin_authenticated', None)
        return False
    
    # Update last activity time
    session['last_activity'] = datetime.utcnow().isoformat()
    return True


def login_required(f):
    """Decorator to require admin login for views."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not is_authenticated():
            return redirect(url_for('admin.login_view'))
        return f(*args, **kwargs)
    return wrapper


def check_rate_limit(ip_address):
    """Check if the IP has exceeded the login attempt rate limit."""
    now = datetime.utcnow()
    
    # Clear old attempts
    for ip in list(login_attempts.keys()):
        if (now - login_attempts[ip]['timestamp']).total_seconds() > LOGIN_COOLDOWN:
            del login_attempts[ip]
    
    # Check current IP
    if ip_address in login_attempts:
        attempts = login_attempts[ip_address]
        if attempts['count'] >= MAX_LOGIN_ATTEMPTS:
            time_diff = (now - attempts['timestamp']).total_seconds()
            if time_diff < LOGIN_COOLDOWN:
                return False
            # Reset if cooldown period has passed
            login_attempts[ip_address] = {'count': 1, 'timestamp': now}
        else:
            login_attempts[ip_address]['count'] += 1
    else:
        login_attempts[ip_address] = {'count': 1, 'timestamp': now}
    
    return True


def upload_to_s3(file_stream, bucket, key, content_type, extra_args=None):
    """Upload a file to an S3 bucket with proper error handling."""
    if extra_args is None:
        extra_args = {}
    
    # Ensure ContentType is set
    if 'ContentType' not in extra_args:
        extra_args['ContentType'] = content_type
    
    try:
        # CRITICAL FIX: Reset the file pointer to the beginning
        file_stream.seek(0)
        
        # Debug: Check file size
        initial_position = file_stream.tell()
        file_stream.seek(0, os.SEEK_END)
        file_size = file_stream.tell()
        file_stream.seek(0)  # Reset again for upload
        
        print(f"Debug - Initial position: {initial_position}, File size: {file_size} bytes")
        
        if file_size == 0:
            print("Warning: File stream is empty")
            return False
        
        # Use the optimized S3Client directly
        from utils.s3_client import S3Client
        
        return S3Client.upload_fileobj(
            file_stream,
            key,
            extra_args
        )
            
    except Exception as e:
        # Enhanced error logging
        import traceback
        print(f"Error uploading file to S3: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return False


class SecureModelView(ModelView):
    """Base model view with security controls."""
    def is_accessible(self):
        return is_authenticated()

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('admin.login_view'))


class StoryModelView(SecureModelView):
    """Admin view for managing stories."""
    column_list = ('id', 'title', 'author', 'created_at', 'updated_at')
    column_searchable_list = ('title', 'author', 'content')
    column_filters = ('author', 'created_at')
    form_excluded_columns = ('created_at', 'updated_at', 's3_cover_key', 'id') 
    
    # Add preview of cover image
    column_formatters = {
        'cover_filename': lambda v, c, m, p: f'<img src="{Config.get_s3_url(m.s3_cover_key)}" width="100">' 
                                             if m.s3_cover_key else ''
    }
    
    column_formatters_args = {
        'cover_filename': {'allow_html': True},
    }

    # No base_path since we use in-memory uploads
    form_extra_fields = {
        'cover_upload': FileUploadField(
            'Cover Image',
            base_path='/tmp',
            allowed_extensions=ALLOWED_EXTENSIONS
        )
    }

    form_widget_args = {
        'content': {'rows': 20},
        'description': {'rows': 5}
    }

    def on_model_change(self, form, model, is_created):
        """Handle model changes including file uploads."""
        # Make sure we don't set ID for new objects
        if is_created:
            # Ensure ID is None for new records to let the database assign it
            model.id = None
            
        file_storage = form.cover_upload.data
        if file_storage and file_storage.filename:
            try:
                # Process and upload the file
                original_filename = secure_filename(file_storage.filename)
                unique_filename = f"{uuid.uuid4()}_{original_filename}"
                s3_key = f"{S3_COVERS_PREFIX}{unique_filename}"
                
                # Determine content type
                content_type = mimetypes.guess_type(original_filename)[0] or 'application/octet-stream'
                
                # IMPORTANT: Reset the file stream position to the beginning
                file_storage.stream.seek(0)
                
                # Get file size to verify it's not empty
                file_storage.stream.seek(0, os.SEEK_END)
                size = file_storage.stream.tell()
                file_storage.stream.seek(0)  # Reset again after checking size
                
                if size == 0:
                    flash("Error: File appears to be empty", 'error')
                    return
                
                # Upload to S3
                upload_success = upload_to_s3(
                    file_storage.stream,
                    Config.S3_BUCKET,
                    s3_key,
                    content_type
                )
                
                if upload_success:
                    model.cover_filename = unique_filename
                    model.s3_cover_key = s3_key
                else:
                    flash("Failed to upload cover image", 'error')
            except Exception as e:
                flash(f"Error processing cover image: {str(e)}", 'error')
                print(f"Error details: {e}")  # Add more detailed logging
                db.session.rollback()
                raise

class CustomAdminIndexView(AdminIndexView):
    """Custom admin index view with authentication."""
    @expose('/')
    def index(self):
        if not is_authenticated():
            return redirect(url_for('.login_view'))
        return super().index()

    @expose('/login', methods=['GET', 'POST'])
    def login_view(self):
        """Handle admin login with rate limiting."""
        if request.method == 'POST':
            # Check rate limiting
            if not check_rate_limit(request.remote_addr):
                flash('Too many login attempts. Please try again later.', 'error')
                return self.render('admin/login.html')
            
            # Verify password
            password = request.form.get('password', '')
            authenticated = False
            
            if ADMIN_PASSWORD_HASH:
                # Use hashed password if available
                authenticated = check_password_hash(ADMIN_PASSWORD_HASH, password)
            else:
                # Fallback to plain text password
                authenticated = password == ADMIN_PASSWORD
            
            if authenticated:
                session['admin_authenticated'] = True
                session['last_activity'] = datetime.utcnow().isoformat()
                flash('Login successful', 'success')
                return redirect(url_for('.index'))
            
            flash('Invalid password', 'error')
        
        return self.render('admin/login.html')

    @expose('/logout')
    def logout_view(self):
        """Handle admin logout."""
        session.pop('admin_authenticated', None)
        session.pop('last_activity', None)
        flash('You have been logged out', 'success')
        return redirect(url_for('.login_view'))


def create_login_template(app):
    """Create login template if it doesn't exist."""
    admin_templates_dir = os.path.join(app.root_path, 'templates', 'admin')
    os.makedirs(admin_templates_dir, exist_ok=True)

    login_template_path = os.path.join(admin_templates_dir, 'login.html')
    if not os.path.exists(login_template_path):
        with open(login_template_path, 'w') as f:
            f.write(
                """{% extends 'admin/master.html' %}
{% block body %}
<div class="container">
  <div class="row">
    <div class="col-md-4 offset-md-4">
      <div class="card mt-5">
        <div class="card-header">
          <h3 class="text-center">StoryVoice Admin Login</h3>
        </div>
        <div class="card-body">
          {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
              {% for category, message in messages %}
                <div class="alert alert-{{ category }}">{{ message }}</div>
              {% endfor %}
            {% endif %}
          {% endwith %}
          <form method="POST">
            <div class="form-group">
              <label for="password">Password</label>
              <input type="password" class="form-control" id="password" name="password" required>
            </div>
            <button type="submit" class="btn btn-primary btn-block mt-3">Login</button>
          </form>
        </div>
      </div>
    </div>
  </div>
</div>
{% endblock %}"""
            )

class UserModelView(ModelView):
    """Admin view for managing users"""
    
    column_list = ('id', 'email', 'email_confirmed', 'is_active', 'last_login', 'created_at')
    
    column_searchable_list = ('email',)
    
    column_filters = ('email_confirmed', 'is_active', 'created_at', 'last_login')
    
    form_columns = ('email', 'password_hash', 'email_confirmed', 'is_active')
    
    form_widget_args = {
        'password_hash': {
            'readonly': True,
            'description': 'To set a password, use the "Set Password" action below.'
        }
    }
    
    column_descriptions = {
        'email_confirmed': 'Whether the user has confirmed their email address',
        'is_active': 'Whether the user account is active (can log in)',
    }
    
    column_formatters = {
        'last_login': lambda v, c, m, p: m.last_login.strftime('%Y-%m-%d %H:%M:%S') if m.last_login else 'Never'
    }
    
    # Create a form with password field for user creation
    def create_form(self):
        form = super(UserModelView, self).create_form()
        # Clear the password_hash field if it exists in the form
        if hasattr(form, 'password_hash'):
            form.password_hash.data = None
        return form
    
    # Override create model to set password properly
    def on_model_change(self, form, model, is_created):
        # If creating a new user and password_hash is empty, set a default password
        if is_created and not model.password_hash:
            model.password_hash = generate_password_hash('changeme')
            flash('User created with default password: "changeme". Please change this immediately.', 'warning')
    
    # Add custom actions
    @staticmethod
    def reset_password_action(ids):
        """Custom action to reset a user's password"""
        try:
            for user_id in ids:
                user = User.query.get(user_id)
                if user:
                    user.password_hash = generate_password_hash('changeme')
            
            from database import db
            db.session.commit()
            
            if len(ids) == 1:
                flash(f'Password reset to "changeme" for 1 user', 'success')
            else:
                flash(f'Password reset to "changeme" for {len(ids)} users', 'success')
            
            return True
        except Exception as e:
            flash(f'Failed to reset password: {str(e)}', 'error')
            return False
        
def init_admin(app):
    """Initialize the admin interface."""
    # Create login template
    create_login_template(app)
    
    # Setup admin interface
    admin = Admin(
        app,
        name='StoryVoice Admin',
        template_mode='bootstrap4',
        index_view=CustomAdminIndexView()
    )
    
    # Add views correctly - using the appropriate view class for each model
    admin.add_view(StoryModelView(Story, db.session, name='Stories'))
    admin.add_view(UserModelView(User, db.session, name='Users'))
    
    # Setup session configuration
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(
        seconds=int(os.getenv('SESSION_TIMEOUT', DEFAULT_SESSION_TIMEOUT))
    )
    
    return admin