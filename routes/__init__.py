from flask import Blueprint

# Create blueprints
voice_bp = Blueprint('voice_api', __name__)
story_bp = Blueprint('story_api', __name__)
audio_bp = Blueprint('audio_api', __name__)
static_bp = Blueprint('static_pages', __name__)
auth_bp = Blueprint('auth_api', __name__, url_prefix='/auth')


# Import routes to register with blueprints
from routes import voice_routes, story_routes, audio_routes, static_routes, auth_routes

def register_blueprints(app):
    """Register all blueprints with the Flask app"""
    app.register_blueprint(voice_bp)
    app.register_blueprint(story_bp)
    app.register_blueprint(audio_bp)
    app.register_blueprint(static_bp)
    app.register_blueprint(auth_bp)