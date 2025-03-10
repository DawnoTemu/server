from flask_admin import Admin, AdminIndexView, expose
from flask_admin.contrib.sqla import ModelView
from flask import redirect, url_for, request, flash, session
from database import db
from models.story_model import Story
from functools import wraps
import os

# Get the admin password from environment variable or use a default for development
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'storyvoice_admin')

def is_authenticated():
    """Check if admin is authenticated"""
    return session.get('admin_authenticated', False)

def login_required(f):
    """Decorator to require login for admin views"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_authenticated():
            return redirect(url_for('admin.login_view'))
        return f(*args, **kwargs)
    return decorated_function

class SecureModelView(ModelView):
    """Base ModelView that implements authentication"""
    
    def is_accessible(self):
        return is_authenticated()
    
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('admin.login_view'))

class StoryModelView(SecureModelView):
    """Admin view for the Story model"""
    column_list = ('id', 'title', 'author', 'created_at', 'updated_at')
    column_searchable_list = ('title', 'author', 'content')
    column_filters = ('author', 'created_at')
    form_excluded_columns = ('created_at', 'updated_at')
    
    # Allow viewing and editing the content in a larger text area
    form_widget_args = {
        'content': {
            'rows': 20
        },
        'description': {
            'rows': 5
        }
    }

class CustomAdminIndexView(AdminIndexView):
    """Custom admin index view with login functionality"""
    
    @expose('/')
    def index(self):
        if not is_authenticated():
            return redirect(url_for('.login_view'))
        return super(CustomAdminIndexView, self).index()
    
    @expose('/login', methods=['GET', 'POST'])
    def login_view(self):
        if request.method == 'POST':
            password = request.form.get('password')
            
            if password == ADMIN_PASSWORD:
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
    """Initialize the admin interface"""
    
    # Create admin interface
    admin = Admin(app, 
                 name='StoryVoice Admin', 
                 template_mode='bootstrap4',
                 index_view=CustomAdminIndexView())
    
    # Add views
    admin.add_view(StoryModelView(Story, db.session, name='Stories'))
    
    # Create login template folder if it doesn't exist
    admin_templates_dir = os.path.join(app.root_path, 'templates', 'admin')
    os.makedirs(admin_templates_dir, exist_ok=True)
    
    # Create login template
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