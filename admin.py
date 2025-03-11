import os
import uuid
import mimetypes
from functools import wraps

from flask import redirect, url_for, request, flash, session
from flask_admin import Admin, AdminIndexView, expose
from flask_admin.contrib.sqla import ModelView
from flask_admin.form import FileUploadField
from werkzeug.utils import secure_filename

from database import db
from models.story_model import Story
from config import Config

# Use environment variable for admin password or default for development
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'storyvoice_admin')

def is_authenticated():
    return session.get('admin_authenticated', False)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_authenticated():
            return redirect(url_for('admin.login_view'))
        return f(*args, **kwargs)
    return decorated_function

def get_content_type(filename):
    file_ext = os.path.splitext(filename)[1].lower()
    content_type = mimetypes.guess_type(filename)[0]
    if not content_type:
        mapping = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.svg': 'image/svg+xml'
        }
        content_type = mapping.get(file_ext, 'application/octet-stream')
    return content_type

class SecureModelView(ModelView):
    def is_accessible(self):
        return is_authenticated()
    
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('admin.login_view'))

class StoryModelView(SecureModelView):
    column_list = ('id', 'title', 'author', 'created_at', 'updated_at')
    column_searchable_list = ('title', 'author', 'content')
    column_filters = ('author', 'created_at')
    form_excluded_columns = ('created_at', 'updated_at')
    
    # Temporary upload directory for file uploads
    temp_upload_path = os.path.join(os.path.dirname(__file__), 'temp_uploads')
    os.makedirs(temp_upload_path, exist_ok=True)
    
    form_extra_fields = {
        'cover_upload': FileUploadField('Cover Image', 
                                        base_path=temp_upload_path,
                                        allowed_extensions=['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg'])
    }
    
    form_widget_args = {
        'content': {'rows': 20},
        'description': {'rows': 5}
    }
    
    def on_model_change(self, form, model, is_created):
        if form.cover_upload.data:
            file_storage = form.cover_upload.data
            original_filename = secure_filename(file_storage.filename)
            unique_filename = f"{uuid.uuid4()}_{original_filename}"
            file_path = os.path.join(self.temp_upload_path, unique_filename)
            
            # Save file locally
            file_storage.save(file_path)
            
            # Prepare S3 upload details
            s3_key = f"covers/{unique_filename}"
            content_type = get_content_type(original_filename)
            
            try:
                s3_client = Config.get_s3_client()
                with open(file_path, 'rb') as file_obj:
                    s3_client.upload_fileobj(
                        file_obj,
                        Config.S3_BUCKET,
                        s3_key,
                        ExtraArgs={'ContentType': content_type}
                    )
                # Update model with S3 info
                model.cover_filename = unique_filename
                model.s3_cover_key = s3_key
                os.remove(file_path)
            except Exception as e:
                flash(f"Error uploading file to S3: {str(e)}", 'error')
                raise

class CustomAdminIndexView(AdminIndexView):
    @expose('/')
    def index(self):
        if not is_authenticated():
            return redirect(url_for('.login_view'))
        return super(CustomAdminIndexView, self).index()
    
    @expose('/login', methods=['GET', 'POST'])
    def login_view(self):
        if request.method == 'POST':
            if request.form.get('password') == ADMIN_PASSWORD:
                session['admin_authenticated'] = True
                flash('Login successful', 'success')
                return redirect(url_for('.index'))
            else:
                flash('Invalid password', 'error')
        return self.render('admin/login.html')
    
    @expose('/logout')
    def logout_view(self):
        session.pop('admin_authenticated', None)
        flash('You have been logged out', 'success')
        return redirect(url_for('.login_view'))

def init_admin(app):
    admin = Admin(app, 
                  name='StoryVoice Admin', 
                  template_mode='bootstrap4',
                  index_view=CustomAdminIndexView())
    
    admin.add_view(StoryModelView(Story, db.session, name='Stories'))
    
    # Ensure the admin template directory exists
    admin_templates_dir = os.path.join(app.root_path, 'templates', 'admin')
    os.makedirs(admin_templates_dir, exist_ok=True)
    
    # Ensure the temporary uploads folder exists
    temp_uploads_dir = os.path.join(app.root_path, 'temp_uploads')
    os.makedirs(temp_uploads_dir, exist_ok=True)
    
    # Create a default login template if it doesn't exist
    login_template_path = os.path.join(admin_templates_dir, 'login.html')
    if not os.path.exists(login_template_path):
        with open(login_template_path, 'w') as f:
            f.write('''
{% extends 'admin/master.html' %}
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
{% endblock %}
''')
    
    return admin