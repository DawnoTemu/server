import os
import uuid
import mimetypes
import time
from functools import wraps
from datetime import datetime, timedelta

from flask import redirect, url_for, request, flash, session
from flask_admin import Admin, AdminIndexView, BaseView, expose
from flask_admin.contrib.sqla import ModelView
from flask import flash, redirect, url_for
from werkzeug.security import generate_password_hash
from models.user_model import User
from flask_admin.form import FileUploadField
from markupsafe import Markup
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash

from database import db
from models.story_model import Story
from models.user_model import User
from models.voice_model import (
    Voice,
    VoiceModel,
    VoiceAllocationStatus,
    VoiceStatus,
    VoiceSlotEvent,
    VoiceSlotEventType,
)
from models.audio_model import AudioStory, AudioStatus
from models.credit_model import CreditLot, CreditTransaction
from config import Config
from utils.credits import calculate_required_credits
from utils.voice_slot_queue import VoiceSlotQueue
from utils.voice_service import VoiceService

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


class SecureBaseView(BaseView):
    """Base non-model view with admin authentication."""

    def is_accessible(self):
        return is_authenticated()

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('admin.login_view'))


class StoryModelView(SecureModelView):
    """Admin view for managing stories."""
    list_template = 'admin/story/list.html'
    create_template = 'admin/model/create.html'
    edit_template = 'admin/model/edit.html'

    column_list = ('id', 'title', 'author', 'credits_cost', 'created_at', 'updated_at')
    column_searchable_list = ('title', 'author', 'content')
    column_filters = ('author', 'created_at')
    form_excluded_columns = ('created_at', 'updated_at', 's3_cover_key', 'id')
    column_labels = {
        'credits_cost': 'Credits',
    }
    
    # Add preview of cover image
    column_formatters = {
        'cover_filename': lambda v, c, m, p: f'<img src="{Config.get_s3_url(m.s3_cover_key)}" width="100">' 
                                             if m.s3_cover_key else ''
        ,
        'credits_cost': lambda v, c, m, p: calculate_required_credits((m.content or ''))
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


class VoiceSlotDashboardView(SecureBaseView):
    """Custom admin dashboard for viewing and managing voice slot usage."""

    def _voice_row(self, voice):
        warm_seconds = getattr(Config, "VOICE_WARM_HOLD_SECONDS", 0) or 0
        hold_expires = None
        if voice.last_used_at and warm_seconds:
            hold_expires = voice.last_used_at + timedelta(seconds=warm_seconds)
        queue_position = VoiceSlotQueue.position(voice.id)
        queue_length = VoiceSlotQueue.length()
        return {
            "voice": voice,
            "user_email": voice.user.email if getattr(voice, "user", None) else "—",
            "remote_id": voice.elevenlabs_voice_id,
            "hold_expires": hold_expires,
            "queue_position": queue_position,
            "queue_length": queue_length,
        }

    @expose('/')
    def index(self):
        ready_voices = (
            Voice.query.filter(Voice.allocation_status == VoiceAllocationStatus.READY)
            .order_by(Voice.updated_at.desc())
            .all()
        )
        allocating_voices = (
            Voice.query.filter(Voice.allocation_status == VoiceAllocationStatus.ALLOCATING)
            .order_by(Voice.updated_at.desc())
            .all()
        )
        ready_rows = [self._voice_row(v) for v in ready_voices]
        allocating_rows = [self._voice_row(v) for v in allocating_voices]

        snapshot = VoiceSlotQueue.snapshot(limit=None)
        now_ts = time.time()
        queue_entries = []
        for item in snapshot:
            voice_id = int(item.get("voice_id")) if item.get("voice_id") is not None else None
            voice = Voice.query.get(voice_id) if voice_id else None
            score = item.get("score")
            available_at = datetime.fromtimestamp(score) if score else None
            wait_seconds = max(0, int(score - now_ts)) if score else 0
            entry = {
                "voice_id": voice_id,
                "voice_name": (voice.name if voice else item.get("voice_name")) or "—",
                "user_email": voice.user.email if voice and getattr(voice, "user", None) else "—",
                "attempts": item.get("attempts", 0),
                "available_at": available_at,
                "wait_display": f"{wait_seconds}s" if wait_seconds else "ready",
            }
            queue_entries.append(entry)

        slot_limit = getattr(Config, "ELEVENLABS_SLOT_LIMIT", 0) or "∞"
        try:
            available_capacity = VoiceModel.available_slot_capacity()
            if available_capacity == float("inf"):
                available_capacity = "∞"
        except Exception:
            available_capacity = "—"

        stats = {
            "active_count": len(ready_rows) + len(allocating_rows),
            "slot_limit": slot_limit,
            "queue_length": VoiceSlotQueue.length(),
            "available_capacity": available_capacity,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        }

        events = VoiceModel.recent_slot_events(30)

        return self.render(
            'admin/voice_slots.html',
            stats=stats,
            ready=ready_rows,
            allocating=allocating_rows,
            queue_entries=queue_entries,
            events=events,
        )

    @expose('/evict/<int:voice_id>', methods=['POST'])
    def evict_voice(self, voice_id: int):
        voice = Voice.query.get(voice_id)
        if not voice:
            flash(f"Voice {voice_id} not found", 'error')
            return redirect(url_for('voice_slots.index'))

        try:
            if voice.elevenlabs_voice_id:
                success, message = VoiceService.delete_voice(
                    voice_id=voice.id,
                    external_voice_id=voice.elevenlabs_voice_id,
                    service=voice.service_provider,
                )
                if not success:
                    flash(f"Remote delete failed: {message}", 'warning')

            VoiceSlotQueue.remove(voice.id)

            voice.elevenlabs_voice_id = None
            voice.elevenlabs_allocated_at = None
            voice.slot_lock_expires_at = None
            voice.allocation_status = VoiceAllocationStatus.RECORDED
            voice.status = VoiceStatus.RECORDED
            voice.last_used_at = datetime.utcnow()
            VoiceSlotEvent.log_event(
                voice_id=voice.id,
                user_id=voice.user_id,
                event_type=VoiceSlotEventType.SLOT_EVICTED,
                reason="admin_manual_evict",
                metadata={"admin": True},
            )
            db.session.commit()
            flash(f"Released slot for voice {voice_id}", 'success')
        except Exception as exc:
            db.session.rollback()
            flash(f"Failed to evict voice {voice_id}: {exc}", 'error')

        return redirect(url_for('voice_slots.index'))

    @expose('/remove-queue/<int:voice_id>', methods=['POST'])
    def remove_queue(self, voice_id: int):
        try:
            VoiceSlotQueue.remove(voice_id)
            voice = Voice.query.get(voice_id)
            if voice:
                VoiceSlotEvent.log_event(
                    voice_id=voice.id,
                    user_id=voice.user_id,
                    event_type=VoiceSlotEventType.ALLOCATION_FAILED,
                    reason="admin_queue_removed",
                    metadata={"admin": True},
                )
                db.session.commit()
            flash(f"Removed voice {voice_id} from queue", 'success')
        except Exception as exc:
            db.session.rollback()
            flash(f"Failed to remove queue entry: {exc}", 'error')

        return redirect(url_for('voice_slots.index'))

class CustomAdminIndexView(AdminIndexView):
    """Custom admin index view with authentication."""
    @expose('/')
    def index(self):
        if not is_authenticated():
            return redirect(url_for('.login_view'))

        # Gather dashboard statistics
        from datetime import datetime, timedelta
        from sqlalchemy import func

        today = datetime.utcnow().date()

        # User stats
        total_users = User.query.count()
        new_users_today = User.query.filter(
            func.date(User.created_at) == today
        ).count() if total_users > 0 else 0

        # Voice stats
        total_voices = Voice.query.count()
        active_slots = Voice.query.filter(
            Voice.allocation_status == VoiceAllocationStatus.READY
        ).count()
        slot_limit = Config.ELEVENLABS_SLOT_LIMIT

        # Audio stats
        total_audio_stories = AudioStory.query.count()
        processing_audio = AudioStory.query.filter(
            AudioStory.status.in_(['pending', 'processing'])
        ).count()

        # Credits stats
        total_credits = db.session.query(func.sum(CreditLot.amount_granted)).scalar() or 0
        credits_used = db.session.query(
            func.sum(CreditLot.amount_granted - CreditLot.amount_remaining)
        ).scalar() or 0

        # Queue stats
        queue_length = VoiceSlotQueue.length()

        # Recent activity
        recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
        recent_audio = AudioStory.query.order_by(AudioStory.created_at.desc()).limit(5).all()

        # First user ID for grant credits quick action
        first_user = User.query.first()
        first_user_id = first_user.id if first_user else None

        return self.render(
            'admin/index.html',
            total_users=total_users,
            new_users_today=new_users_today,
            total_voices=total_voices,
            active_slots=active_slots,
            slot_limit=slot_limit,
            total_audio_stories=total_audio_stories,
            processing_audio=processing_audio,
            total_credits=total_credits,
            credits_used=credits_used,
            queue_length=queue_length,
            recent_users=recent_users,
            recent_audio=recent_audio,
            first_user_id=first_user_id
        )

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

def create_user_credits_template(app):
    """Create user credits template if it doesn't exist."""
    admin_templates_dir = os.path.join(app.root_path, 'templates', 'admin')
    os.makedirs(admin_templates_dir, exist_ok=True)
    tpl_path = os.path.join(admin_templates_dir, 'user_credits.html')
    if not os.path.exists(tpl_path):
        with open(tpl_path, 'w') as f:
            f.write(
                """{% extends 'admin/master.html' %}
{% block body %}
<div class="container">
  <div class="row">
    <div class="col-md-10 offset-md-1">
      <div class="card mt-4">
        <div class="card-header">
          <h3>User Credits</h3>
          <p>User: {{ user.email }} (ID: {{ user.id }}) — Balance: {{ user.credits_balance }}</p>
        </div>
        <div class="card-body">
          <h5>Active Lots</h5>
          <table class="table table-sm table-striped">
            <thead><tr><th>Source</th><th>Remaining</th><th>Expires At</th><th>Created</th></tr></thead>
            <tbody>
              {% for lot in lots %}
              <tr>
                <td>{{ lot.source }}</td>
                <td>{{ lot.amount_remaining }}</td>
                <td>{% if lot.expires_at %}{{ lot.expires_at }}{% else %}—{% endif %}</td>
                <td>{{ lot.created_at }}</td>
              </tr>
              {% else %}
              <tr><td colspan="4" class="text-center">No active lots</td></tr>
              {% endfor %}
            </tbody>
          </table>

          <h5 class="mt-4">Recent Transactions</h5>
          <table class="table table-sm table-striped">
            <thead><tr><th>At</th><th>Type</th><th>Amount</th><th>Status</th><th>Reason</th><th>Audio ID</th><th>Story ID</th></tr></thead>
            <tbody>
              {% for tx in transactions %}
              <tr>
                <td>{{ tx.created_at }}</td>
                <td>{{ tx.type }}</td>
                <td>{{ tx.amount }}</td>
                <td>{{ tx.status }}</td>
                <td>{{ tx.reason }}</td>
                <td>{{ tx.audio_story_id or '—' }}</td>
                <td>{{ tx.story_id or '—' }}</td>
              </tr>
              {% else %}
              <tr><td colspan="7" class="text-center">No transactions</td></tr>
              {% endfor %}
            </tbody>
          </table>

          <a href="{{ url_for('user.index_view') }}" class="btn btn-secondary">Back</a>
          <a href="{{ url_for('user.grant_credits_view') }}?id={{ user.id }}" class="btn btn-primary ms-2">Grant Points</a>
        </div>
      </div>
    </div>
  </div>
</div>
{% endblock %}
"""
            )

def create_voice_slots_template(app):
    """Create the voice slots dashboard template if missing."""
    admin_templates_dir = os.path.join(app.root_path, 'templates', 'admin')
    os.makedirs(admin_templates_dir, exist_ok=True)
    tpl_path = os.path.join(admin_templates_dir, 'voice_slots.html')
    if not os.path.exists(tpl_path):
        with open(tpl_path, 'w') as f:
            f.write(
                """{% extends 'admin/master.html' %}
{% block body %}
<div class="container-fluid mt-4">
  <h2>Voice Slot Dashboard</h2>
  <p class="text-muted">Snapshot taken at {{ stats.generated_at }}</p>
  <div class="row mt-3">
    <div class="col-md-3">
      <div class="card border-primary mb-3">
        <div class="card-header">Active Slots</div>
        <div class="card-body">
          <h4 class="card-title">{{ stats.active_count }} / {{ stats.slot_limit }}</h4>
          <p class="card-text">Available capacity: {{ stats.available_capacity }}</p>
        </div>
      </div>
    </div>
    <div class="col-md-3">
      <div class="card border-info mb-3">
        <div class="card-header">Allocating</div>
        <div class="card-body">
          <h4 class="card-title">{{ allocating|length }}</h4>
          <p class="card-text">Voices currently acquiring slots.</p>
        </div>
      </div>
    </div>
    <div class="col-md-3">
      <div class="card border-success mb-3">
        <div class="card-header">Ready</div>
        <div class="card-body">
          <h4 class="card-title">{{ ready|length }}</h4>
          <p class="card-text">Voices with active remote slots.</p>
        </div>
      </div>
    </div>
    <div class="col-md-3">
      <div class="card border-warning mb-3">
        <div class="card-header">Queued</div>
        <div class="card-body">
          <h4 class="card-title">{{ stats.queue_length }}</h4>
          <p class="card-text">Pending allocation requests.</p>
        </div>
      </div>
    </div>
  </div>

  <h4 class="mt-4">Ready Voices</h4>
  <div class="table-responsive">
    <table class="table table-sm table-striped align-middle">
      <thead>
        <tr>
          <th>ID</th>
          <th>User</th>
          <th>Name</th>
          <th>Remote ID</th>
          <th>Allocated</th>
          <th>Last Used</th>
          <th>Hold Expires</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        {% for row in ready %}
        <tr>
          <td>{{ row.voice.id }}</td>
          <td>{{ row.user_email }}</td>
          <td>{{ row.voice.name }}</td>
          <td>{{ row.remote_id or '—' }}</td>
          <td>{{ row.voice.elevenlabs_allocated_at or '—' }}</td>
          <td>{{ row.voice.last_used_at or '—' }}</td>
          <td>{{ row.hold_expires or '—' }}</td>
          <td>
            <form method="post" action="{{ url_for('voice_slots.evict_voice', voice_id=row.voice.id) }}" class="d-inline">
              <button type="submit" class="btn btn-sm btn-outline-danger" onclick="return confirm('Release slot for voice {{ row.voice.id }}?');">Evict</button>
            </form>
          </td>
        </tr>
        {% else %}
        <tr><td colspan="8" class="text-center text-muted">No ready voices</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

  <h4 class="mt-4">Allocating Voices</h4>
  <div class="table-responsive">
    <table class="table table-sm table-striped align-middle">
      <thead>
        <tr>
          <th>ID</th>
          <th>User</th>
          <th>Name</th>
          <th>Status</th>
          <th>Queue Position</th>
          <th>Queue Length</th>
          <th>Lock Expires</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        {% for row in allocating %}
        <tr>
          <td>{{ row.voice.id }}</td>
          <td>{{ row.user_email }}</td>
          <td>{{ row.voice.name }}</td>
          <td>{{ row.voice.allocation_status }}</td>
          <td>{{ row.queue_position if row.queue_position is not none else '—' }}</td>
          <td>{{ row.queue_length }}</td>
          <td>{{ row.voice.slot_lock_expires_at or '—' }}</td>
          <td>
            <form method="post" action="{{ url_for('voice_slots.remove_queue', voice_id=row.voice.id) }}" class="d-inline">
              <button type="submit" class="btn btn-sm btn-outline-secondary">Remove Queue</button>
            </form>
            <form method="post" action="{{ url_for('voice_slots.evict_voice', voice_id=row.voice.id) }}" class="d-inline">
              <button type="submit" class="btn btn-sm btn-outline-danger" onclick="return confirm('Cancel allocation and release voice {{ row.voice.id }}?');">Evict</button>
            </form>
          </td>
        </tr>
        {% else %}
        <tr><td colspan="8" class="text-center text-muted">No voices allocating</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

  <h4 class="mt-4">Queued Requests</h4>
  <div class="table-responsive">
    <table class="table table-sm table-striped align-middle">
      <thead>
        <tr>
          <th>Voice ID</th>
          <th>User</th>
          <th>Name</th>
          <th>Attempts</th>
          <th>ETA</th>
          <th>Available In</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        {% for entry in queue_entries %}
        <tr>
          <td>{{ entry.voice_id }}</td>
          <td>{{ entry.user_email }}</td>
          <td>{{ entry.voice_name }}</td>
          <td>{{ entry.attempts }}</td>
          <td>{{ entry.available_at or '—' }}</td>
          <td>{{ entry.wait_display }}</td>
          <td>
            <form method="post" action="{{ url_for('voice_slots.remove_queue', voice_id=entry.voice_id) }}" class="d-inline">
              <button type="submit" class="btn btn-sm btn-outline-secondary">Remove</button>
            </form>
          </td>
        </tr>
        {% else %}
        <tr><td colspan="7" class="text-center text-muted">Queue is empty</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

  <h4 class="mt-4">Recent Slot Events</h4>
  <div class="table-responsive">
    <table class="table table-sm table-striped align-middle">
      <thead>
        <tr>
          <th>Time</th>
          <th>Voice</th>
          <th>User</th>
          <th>Event</th>
          <th>Reason</th>
          <th>Metadata</th>
        </tr>
      </thead>
      <tbody>
        {% for event in events %}
        <tr>
          <td>{{ event.created_at }}</td>
          <td>{{ event.voice_id or '—' }}</td>
          <td>{{ event.user_id or '—' }}</td>
          <td>{{ event.event_type }}</td>
          <td>{{ event.reason or '—' }}</td>
          <td><small>{{ event.metadata }}</small></td>
        </tr>
        {% else %}
        <tr><td colspan="6" class="text-center text-muted">No recent events</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endblock %}
"""
            )
def create_grant_template(app):
    """Create grant credits template if missing."""
    admin_templates_dir = os.path.join(app.root_path, 'templates', 'admin')
    os.makedirs(admin_templates_dir, exist_ok=True)
    grant_template_path = os.path.join(admin_templates_dir, 'grant_credits.html')
    if not os.path.exists(grant_template_path):
        with open(grant_template_path, 'w') as f:
            f.write(
                """{% extends 'admin/master.html' %}
{% block body %}
<div class="container">
  <div class="row">
    <div class="col-md-6 offset-md-3">
      <div class="card mt-5">
        <div class="card-header">
          <h3 class="text-center">Grant Story Points</h3>
          <p>User: {{ user.email }} (ID: {{ user.id }})</p>
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
            <input type="hidden" name="user_id" value="{{ user.id }}" />
            <div class="form-group">
              <label for="amount">Amount (points)</label>
              <input type="number" min="1" class="form-control" id="amount" name="amount" required>
            </div>
            <div class="form-group mt-2">
              <label for="reason">Reason</label>
              <input type="text" class="form-control" id="reason" name="reason" placeholder="admin_grant">
            </div>
            <div class="form-group mt-2">
              <label for="source">Source</label>
              <select class="form-control" id="source" name="source">
                <option value="add_on">add_on</option>
                <option value="referral">referral</option>
                <option value="free">free</option>
                <option value="monthly">monthly</option>
                <option value="event">event</option>
              </select>
            </div>
            <div class="form-group mt-2">
              <label for="expires_at">Expires At (ISO8601, optional)</label>
              <input type="text" class="form-control" id="expires_at" name="expires_at" placeholder="2025-12-31T23:59:59Z">
            </div>
            <button type="submit" class="btn btn-primary btn-block mt-3">Grant Points</button>
            <a href="{{ url_for('user.index_view') }}" class="btn btn-secondary btn-block mt-2">Back</a>
          </form>
        </div>
      </div>
    </div>
  </div>
  </div>
{% endblock %}
"""
            )

class UserModelView(SecureModelView):
    """Admin view for managing users"""
    list_template = 'admin/user/list.html'
    create_template = 'admin/model/create.html'
    edit_template = 'admin/model/edit.html'

    column_list = ('id', 'email', 'credits_balance', 'manage_credits', 'email_confirmed', 'is_active', 'last_login', 'created_at')
    column_labels = {
        'credits_balance': 'Story Points',
        'manage_credits': 'Manage Credits',
    }
    
    column_searchable_list = ('email',)
    
    column_filters = ('email_confirmed', 'is_active', 'created_at', 'last_login', 'credits_balance')
    
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
        'credits_balance': 'Current Story Points available to the user (read-only)',
    }
    
    column_formatters = {
        'last_login': lambda v, c, m, p: m.last_login.strftime('%Y-%m-%d %H:%M:%S') if m.last_login else 'Never',
        'manage_credits': lambda v, c, m, p: Markup(
            f'<a class="btn btn-sm btn-outline-primary" href="{url_for("user.user_credits_view")}?id={m.id}">View</a> '
            f'<a class="btn btn-sm btn-primary" href="{url_for("user.grant_credits_view")}?id={m.id}">Grant</a>'
        )
    }

    # Enable built-in details page
    can_view_details = True
    column_details_list = (
        'id', 'email', 'credits_balance', 'email_confirmed', 'is_active', 'last_login', 'created_at'
    )

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

    @expose('/grant-credits', methods=['GET', 'POST'])
    def grant_credits_view(self):
        """Form to grant Story Points to a single user."""
        if not is_authenticated():
            return redirect(url_for('admin.login_view'))
        from models.user_model import UserModel
        from models.credit_model import grant as credit_grant
        user_id = request.args.get('id') or request.form.get('user_id')
        if not user_id:
            flash('Missing user id', 'error')
            return redirect(url_for('.index_view'))
        try:
            user_id = int(user_id)
        except Exception:
            flash('Invalid user id', 'error')
            return redirect(url_for('.index_view'))

        user = UserModel.get_by_id(user_id)
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('.index_view'))

        if request.method == 'POST':
            try:
                amount = int(request.form.get('amount', '0'))
            except Exception:
                amount = 0
            reason = request.form.get('reason') or 'admin_grant'
            source = (request.form.get('source') or 'add_on').strip().lower()
            expires_at_raw = request.form.get('expires_at')
            expires_at = None
            if expires_at_raw:
                try:
                    expires_at = datetime.fromisoformat(expires_at_raw.replace('Z', '+00:00'))
                except Exception:
                    flash('Invalid expires_at format. Use ISO8601.', 'error')
                    return self.render('admin/grant_credits.html', user=user)
            if amount <= 0:
                flash('Amount must be a positive integer', 'error')
                return self.render('admin/grant_credits.html', user=user)
            try:
                credit_grant(user_id=user.id, amount=amount, reason=reason, source=source, expires_at=expires_at)
                flash(f'Granted {amount} Story Points to {user.email}', 'success')
                return redirect(url_for('.index_view'))
            except Exception as e:
                db.session.rollback()
                flash(f'Failed to grant credits: {e}', 'error')
                return self.render('admin/grant_credits.html', user=user)

        return self.render('admin/grant_credits.html', user=user)

    @expose('/credits', methods=['GET'])
    def user_credits_view(self):
        """Read-only panel showing active lots and recent transactions for a user."""
        if not is_authenticated():
            return redirect(url_for('admin.login_view'))
        from models.user_model import UserModel
        from models.credit_model import CreditLot, CreditTransaction
        user_id = request.args.get('id')
        if not user_id:
            flash('Missing user id', 'error')
            return redirect(url_for('.index_view'))
        try:
            user_id = int(user_id)
        except Exception:
            flash('Invalid user id', 'error')
            return redirect(url_for('.index_view'))

        user = UserModel.get_by_id(user_id)
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('.index_view'))

        now = datetime.utcnow()
        lots = (
            CreditLot.query
            .filter(
                CreditLot.user_id == user.id,
                (CreditLot.expires_at.is_(None) | (CreditLot.expires_at > now)),
                CreditLot.amount_remaining > 0,
            )
            .order_by(CreditLot.expires_at.asc(), CreditLot.created_at)
            .all()
        )
        transactions = (
            CreditTransaction.query
            .filter(CreditTransaction.user_id == user.id)
            .order_by(CreditTransaction.created_at.desc())
            .limit(20)
            .all()
        )
        return self.render('admin/user_credits.html', user=user, lots=lots, transactions=transactions)
    
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
    list_template = 'admin/voice/list.html'
    create_template = 'admin/model/create.html'
    edit_template = 'admin/model/edit.html'

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
    list_template = 'admin/audiostory/list.html'
    create_template = 'admin/model/create.html'
    edit_template = 'admin/model/edit.html'

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
    
    def _refund_audio_action(self, ids):
        from models.credit_model import refund_by_audio
        success = 0
        errors = []
        for audio_id in ids:
            try:
                ok, refund_tx = refund_by_audio(int(audio_id), reason='admin_refund')
                if ok and refund_tx is not None:
                    success += 1
                else:
                    errors.append(f"Audio ID {audio_id}: no outstanding debit to refund")
            except Exception as e:
                db.session.rollback()
                errors.append(f"Audio ID {audio_id}: {e}")
        if success > 0:
            db.session.commit()
        if errors:
            flash(f"Refunded {success} audios. Errors: {', '.join(errors)}", 'warning')
        else:
            flash(f"Refunded {success} audios.", 'success')
        return success > 0
    
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
        actions_list.append(('refund_audio', 'Refund Credits for Selected Audio'))
        
        # Add confirmation messages
        confirmation_messages['delete_audio'] = 'Are you sure you want to delete these audio files and records?'
        confirmation_messages['regenerate_audio'] = 'Are you sure you want to regenerate these audio files?'
        confirmation_messages['refund_audio'] = 'Refund credits for the selected audio items?'
        
        # Return the expected format
        return actions_list, confirmation_messages
    
    # Implement the action handlers
    def action_delete_audio(self, ids):
        return self._delete_audio_action(ids)
    
    def action_regenerate_audio(self, ids):
        return self._regenerate_audio_action(ids)
    
    def action_refund_audio(self, ids):
        return self._refund_audio_action(ids)


class CreditLotModelView(SecureModelView):
    """Read-only admin view for credit lots."""
    list_template = 'admin/creditlot/list.html'

    can_create = False
    can_edit = False
    can_delete = False

    column_list = (
        'id', 'user_id', 'source', 'amount_granted', 'amount_remaining', 'expires_at', 'created_at', 'updated_at'
    )
    column_labels = {
        'user_id': 'User',
        'amount_granted': 'Granted',
        'amount_remaining': 'Remaining',
    }
    column_filters = (
        'user_id', 'source', 'expires_at', 'created_at'
    )
    column_searchable_list = ('source',)

    # Custom action to expire selected lots now
    def _expire_lots_action(self, ids):
        from models.credit_model import CreditLot, CreditTransaction, CreditTransactionAllocation
        from models.user_model import User
        success = 0
        errors = []
        for lot_id in ids:
            lot = CreditLot.query.get(lot_id)
            if not lot:
                errors.append(f"Lot {lot_id}: not found")
                continue
            try:
                delta = int(lot.amount_remaining or 0)
                if delta <= 0:
                    continue
                # Create an 'expire' transaction and allocation to keep ledger consistent
                tx = CreditTransaction(
                    user_id=lot.user_id,
                    amount=-delta,
                    type='expire',
                    reason='admin_expire',
                    audio_story_id=None,
                    story_id=None,
                    status='applied',
                )
                db.session.add(tx)
                db.session.flush()
                db.session.add(
                    CreditTransactionAllocation(transaction_id=tx.id, lot_id=lot.id, amount=-delta)
                )
                # Zero out the lot and adjust cached balance
                lot.amount_remaining = 0
                user = db.session.get(User, lot.user_id)
                if user:
                    user.credits_balance = max(0, int(user.credits_balance or 0) - delta)
                success += 1
            except Exception as e:
                db.session.rollback()
                errors.append(f"Lot {lot_id}: {e}")
        if success > 0:
            db.session.commit()
        if errors:
            flash(f"Expired {success} lots. Errors: {', '.join(errors)}", 'warning')
        else:
            flash(f"Expired {success} lots.", 'success')
        return success > 0

    def get_actions_list(self):
        actions_tuple = super(CreditLotModelView, self).get_actions_list()
        if len(actions_tuple) == 2:
            actions, confirmation_messages = actions_tuple
        else:
            actions = actions_tuple[0] if actions_tuple else []
            confirmation_messages = {}
        actions_list = list(actions) if isinstance(actions, tuple) else actions
        actions_list.append(('expire_lots', 'Expire selected lots now'))
        confirmation_messages['expire_lots'] = 'Expire these lots now and reduce users\' balances?'
        return actions_list, confirmation_messages

    def action_expire_lots(self, ids):
        return self._expire_lots_action(ids)


class CreditTransactionModelView(SecureModelView):
    """Read-only admin view for credit transactions."""
    list_template = 'admin/credittransaction/list.html'

    can_create = False
    can_edit = False
    can_delete = False

    column_list = (
        'id', 'user_id', 'type', 'amount', 'status', 'reason', 'audio_story_id', 'story_id', 'created_at'
    )
    column_labels = {
        'user_id': 'User',
        'audio_story_id': 'Audio ID',
        'story_id': 'Story ID',
    }
    column_filters = (
        'user_id', 'type', 'status', 'created_at'
    )
    column_searchable_list = ('type', 'status', 'reason')

def init_admin(app):
    """Initialize the admin interface."""
    # Create login template
    create_login_template(app)
    create_grant_template(app)
    create_voice_slots_template(app)
    create_user_credits_template(app)
    
    # Setup admin interface
    admin = Admin(
        app,
        name='StoryVoice Admin',
        template_mode='bootstrap4',
        index_view=CustomAdminIndexView()
    )
    
    # Add views correctly - using the appropriate view class for each model
    admin.add_view(VoiceSlotDashboardView(name='Voice Slots', endpoint='voice_slots'))
    admin.add_view(StoryModelView(Story, db.session, name='Stories'))
    admin.add_view(UserModelView(User, db.session, name='Users'))
    admin.add_view(VoiceModelView(Voice, db.session, name='Voices'))
    admin.add_view(AudioStoryModelView(AudioStory, db.session, name='Audio Stories'))
    admin.add_view(CreditLotModelView(CreditLot, db.session, name='Credit Lots'))
    admin.add_view(CreditTransactionModelView(CreditTransaction, db.session, name='Credit Transactions'))

    # Setup session configuration
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(
        seconds=int(os.getenv('SESSION_TIMEOUT', DEFAULT_SESSION_TIMEOUT))
    )
    
    return admin
