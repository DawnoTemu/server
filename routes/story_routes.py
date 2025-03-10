from flask import jsonify, send_from_directory
from routes import story_bp
from controllers.story_controller import StoryController
from config import Config

@story_bp.route('/stories')
def list_stories():
    """API endpoint to list all stories"""
    success, result, status_code = StoryController.get_all_stories()
    
    return jsonify(result), status_code

@story_bp.route('/stories/<int:story_id>')
def get_story(story_id):
    """API endpoint to get a specific story"""
    success, result, status_code = StoryController.get_story(story_id)
    
    return jsonify(result), status_code

@story_bp.route('/stories/<int:story_id>/cover.png')
def get_story_cover(story_id):
    """API endpoint to get a story's cover image"""
    cover_path = StoryController.get_story_cover_path(story_id)
    
    if not cover_path:
        return jsonify({"error": "Cover image not found"}), 404
        
    # Convert Path object to string for Flask compatibility
    return send_from_directory(
        str(Config.STORIES_DIR),
        cover_path.name,
        mimetype='image/png'
    )