from flask import Blueprint

# Create blueprints with appropriate path prefixes
voice_bp = Blueprint('voice_api', __name__)
story_bp = Blueprint('story_api', __name__)
audio_bp = Blueprint('audio_api', __name__)
static_bp = Blueprint('static_pages', __name__)
auth_bp = Blueprint('auth_api', __name__, url_prefix='/auth')
task_bp = Blueprint('task_api', __name__)  # New blueprint for task status checking

# Import routes to register with blueprints
# These imports MUST be after the blueprint definitions
from routes import voice_routes, story_routes, audio_routes, static_routes, auth_routes, task_routes

def register_blueprints(app):
    """Register all blueprints with the Flask app"""
    app.register_blueprint(voice_bp)
    app.register_blueprint(story_bp)
    app.register_blueprint(audio_bp)
    app.register_blueprint(static_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(task_bp)  # Register the new task blueprint