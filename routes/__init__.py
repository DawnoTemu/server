from flask import Blueprint

# Create blueprints
voice_bp = Blueprint('voice', __name__)
story_bp = Blueprint('story', __name__)
audio_bp = Blueprint('audio', __name__)
static_bp = Blueprint('static', __name__)

# Import routes to register with blueprints
from routes import voice_routes, story_routes, audio_routes, static_routes

def register_blueprints(app):
    """Register all blueprints with the Flask app"""
    app.register_blueprint(voice_bp)
    app.register_blueprint(story_bp)
    app.register_blueprint(audio_bp)
    app.register_blueprint(static_bp)