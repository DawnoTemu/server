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
from models.voice_model import Voice, VoiceModel
from models.audio_model import AudioStory, AudioStatus
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

class UserModelView(SecureModelView):
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


class VoiceModelView(SecureModelView):
    """Admin view for managing voices"""
    
    column_list = ('id', 'name', 'user', 'elevenlabs_voice_id', 'created_at')
    
    column_searchable_list = ('name', 'elevenlabs_voice_id')
    
    column_filters = ('user.email', 'name', 'created_at')
    
    column_formatters = {
        'user': lambda v, c, m, p: m.user.email if m.user else None,
    }
    
    column_descriptions = {
        'elevenlabs_voice_id': 'Voice ID from ElevenLabs API',
        'user_id': 'User who owns this voice',
        's3_sample_key': 'S3 key for the original audio sample',
    }
    
    form_columns = ('name', 'elevenlabs_voice_id', 'user', 's3_sample_key', 'sample_filename')
    
    create_modal = True
    edit_modal = True
    
    # Add custom actions
    def _delete_voice_action(self, ids):
        """Custom action to delete a voice from ElevenLabs and database"""
        # Import here to avoid circular imports
        from models.voice_model import VoiceModel
        
        success_count = 0
        error_messages = []
        
        for voice_id in ids:
            success, message = VoiceModel.delete_voice(voice_id)
            if success:
                success_count += 1
            else:
                error_messages.append(f"Voice ID {voice_id}: {message}")
        
        if success_count == len(ids):
            flash(f'Successfully deleted {success_count} voices', 'success')
        else:
            flash(f'Deleted {success_count} of {len(ids)} voices. Errors: {", ".join(error_messages)}', 'warning')
        
        return success_count > 0
    
    # Register custom actions - FIXED VERSION with correct return value
    def get_actions_list(self):
        # Get the original actions and confirmations
        actions_tuple = super(VoiceModelView, self).get_actions_list()
        
        # Unpack the tuple (it should have 2 items)
        if len(actions_tuple) == 2:
            actions, confirmation_messages = actions_tuple
        else:
            # Handle unexpected return value format
            actions = actions_tuple[0] if actions_tuple else []
            confirmation_messages = {}
        
        # Convert to list if necessary
        actions_list = list(actions) if isinstance(actions, tuple) else actions
        
        # Add our custom action
        actions_list.append(('delete_voice', 'Delete from ElevenLabs and Database'))
        
        # Add confirmation message for our action
        confirmation_messages['delete_voice'] = 'Are you sure you want to delete these voices from ElevenLabs and the database?'
        
        # Return the expected format
        return actions_list, confirmation_messages
    
    # Implement the action handler
    def action_delete_voice(self, ids):
        return self._delete_voice_action(ids)


class AudioStoryModelView(SecureModelView):
    """Admin view for managing audio stories"""
    
    column_list = ('id', 'story', 'voice', 'user', 'status', 'created_at', 'updated_at')
    
    column_searchable_list = ('status', 'error_message')
    
    column_filters = (
        'status', 
        'user.email',
        'voice.name', 
        'story.title',
        'created_at',
        'updated_at'
    )
    
    column_formatters = {
        'user': lambda v, c, m, p: m.user.email if m.user else None,
        'story': lambda v, c, m, p: m.story.title if m.story else None,
        'voice': lambda v, c, m, p: m.voice.name if m.voice else None,
        'status': lambda v, c, m, p: m.status,
    }
    
    column_descriptions = {
        'story_id': 'Story that this audio belongs to',
        'voice_id': 'Voice used for synthesis',
        'user_id': 'User who owns this audio',
        'status': 'Current status of the audio (pending, processing, ready, error)',
        'error_message': 'Error message if synthesis failed',
        's3_key': 'S3 key where the audio file is stored',
        'file_size_bytes': 'Size of the audio file in bytes',
        'duration_seconds': 'Duration of the audio in seconds',
    }
    
    form_columns = (
        'story', 
        'voice', 
        'user', 
        'status', 
        'error_message', 
        's3_key', 
        'file_size_bytes', 
        'duration_seconds'
    )
    
    form_choices = {
        'status': [
            (AudioStatus.PENDING.value, 'Pending'),
            (AudioStatus.PROCESSING.value, 'Processing'),
            (AudioStatus.READY.value, 'Ready'),
            (AudioStatus.ERROR.value, 'Error')
        ]
    }
    
    form_widget_args = {
        'error_message': {'rows': 3},
    }
    
    # Add a custom list of status colors
    status_colors = {
        AudioStatus.PENDING.value: 'blue',
        AudioStatus.PROCESSING.value: 'orange',
        AudioStatus.READY.value: 'green',
        AudioStatus.ERROR.value: 'red'
    }
    
    create_modal = True
    edit_modal = True
    
    # Custom actions
    def _delete_audio_action(self, ids):
        """Custom action to delete audio stories and their S3 files"""
        from models.audio_model import AudioModel
        
        success_count = 0
        error_messages = []
        deleted_s3_files = 0
        
        for audio_id in ids:
            try:
                # Get the audio record
                audio = AudioStory.query.get(audio_id)
                
                if not audio:
                    error_messages.append(f"Audio ID {audio_id}: Not found")
                    continue
                
                # Delete S3 file if it exists
                if audio.s3_key:
                    try:
                        from utils.s3_client import S3Client
                        S3Client.delete_objects([audio.s3_key])
                        deleted_s3_files += 1
                    except Exception as e:
                        logger.error(f"Error deleting S3 file for audio {audio_id}: {str(e)}")
                        # Continue with database deletion even if S3 fails
                
                # Delete the database record
                db.session.delete(audio)
                success_count += 1
                
            except Exception as e:
                db.session.rollback()
                error_messages.append(f"Audio ID {audio_id}: {str(e)}")
        
        # Commit all successful deletions
        if success_count > 0:
            db.session.commit()
        
        if error_messages:
            flash(f'Deleted {success_count} audio stories ({deleted_s3_files} S3 files). Errors: {", ".join(error_messages)}', 'warning')
        else:
            flash(f'Successfully deleted {success_count} audio stories ({deleted_s3_files} S3 files)', 'success')
        
        return success_count > 0
    
    def _regenerate_audio_action(self, ids):
        """Custom action to regenerate failed or pending audio stories"""
        from models.audio_model import AudioModel
        from models.story_model import StoryModel
        
        success_count = 0
        error_messages = []
        
        for audio_id in ids:
            try:
                # Get the audio record
                audio = AudioStory.query.get(audio_id)
                
                if not audio:
                    error_messages.append(f"Audio ID {audio_id}: Not found")
                    continue
                
                # Get the story text
                story = StoryModel.get_story_by_id(audio.story_id)
                if not story or 'content' not in story or not story['content']:
                    error_messages.append(f"Audio ID {audio_id}: Story content not found")
                    continue
                
                # Get the voice
                from models.voice_model import Voice
                voice = Voice.query.get(audio.voice_id)
                if not voice or not voice.elevenlabs_voice_id:
                    error_messages.append(f"Audio ID {audio_id}: Voice not found")
                    continue
                
                # Update status to processing
                audio.status = AudioStatus.PROCESSING.value
                audio.error_message = None
                db.session.commit()
                
                # Synthesize speech
                synth_success, audio_data = AudioModel.synthesize_speech(voice.elevenlabs_voice_id, story['content'])
                
                if not synth_success:
                    audio.status = AudioStatus.ERROR.value
                    audio.error_message = str(audio_data)
                    db.session.commit()
                    error_messages.append(f"Audio ID {audio_id}: Synthesis failed - {str(audio_data)}")
                    continue
                
                # Store audio
                store_success, message = AudioModel.store_audio(audio_data, audio.voice_id, audio.story_id, audio)
                
                if not store_success:
                    error_messages.append(f"Audio ID {audio_id}: Storage failed - {message}")
                    continue
                
                success_count += 1
                
            except Exception as e:
                db.session.rollback()
                error_messages.append(f"Audio ID {audio_id}: {str(e)}")
        
        if error_messages:
            flash(f'Regenerated {success_count} audio stories. Errors: {", ".join(error_messages)}', 'warning')
        else:
            flash(f'Successfully regenerated {success_count} audio stories', 'success')
        
        return success_count > 0
    
    # Register custom actions
    def get_actions_list(self):
        # Get the original actions and confirmations
        actions_tuple = super(AudioStoryModelView, self).get_actions_list()
        
        # Unpack the tuple (it should have 2 items)
        if len(actions_tuple) == 2:
            actions, confirmation_messages = actions_tuple
        else:
            # Handle unexpected return value format
            actions = actions_tuple[0] if actions_tuple else []
            confirmation_messages = {}
        
        # Convert to list if necessary
        actions_list = list(actions) if isinstance(actions, tuple) else actions
        
        # Add our custom actions
        actions_list.append(('delete_audio', 'Delete Audio Files and Records'))
        actions_list.append(('regenerate_audio', 'Regenerate Failed Audio'))
        
        # Add confirmation messages
        confirmation_messages['delete_audio'] = 'Are you sure you want to delete these audio files and records?'
        confirmation_messages['regenerate_audio'] = 'Are you sure you want to regenerate these audio files?'
        
        # Return the expected format
        return actions_list, confirmation_messages
    
    # Implement the action handlers
    def action_delete_audio(self, ids):
        return self._delete_audio_action(ids)
    
    def action_regenerate_audio(self, ids):
        return self._regenerate_audio_action(ids)

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
    admin.add_view(VoiceModelView(Voice, db.session, name='Voices'))
    admin.add_view(AudioStoryModelView(AudioStory, db.session, name='Audio Stories'))

    # Setup session configuration
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(
        seconds=int(os.getenv('SESSION_TIMEOUT', DEFAULT_SESSION_TIMEOUT))
    )
    
    return admin