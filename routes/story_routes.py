from flask import jsonify, send_from_directory, redirect
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

@story_bp.route('/stories/<int:story_id>/cover')
def get_story_cover(story_id):
    """API endpoint to get a story's cover image from S3"""
    success, result = StoryController.get_story_cover_presigned_url(story_id)
    if success:
        return redirect(result)
    return jsonify({"error": "Cover image not found"}), 404