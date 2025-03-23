from flask import jsonify, redirect
from routes import story_bp
from controllers.story_controller import StoryController

# GET /stories - List all stories
@story_bp.route('/stories', methods=['GET'])
def list_stories():
    """List all available stories"""
    success, result, status_code = StoryController.get_all_stories()
    return jsonify(result), status_code

# GET /stories/:id - Get a specific story
@story_bp.route('/stories/<int:story_id>', methods=['GET'])
def get_story(story_id):
    """Get a specific story by ID"""
    success, result, status_code = StoryController.get_story(story_id)
    return jsonify(result), status_code

# GET /stories/:id/cover - Get story cover image
@story_bp.route('/stories/<int:story_id>/cover', methods=['GET'])
def get_story_cover(story_id):
    """Get the cover image for a story"""
    success, result = StoryController.get_story_cover_presigned_url(story_id)
    if success:
        return redirect(result)
    return jsonify({"error": "Cover image not found"}), 404