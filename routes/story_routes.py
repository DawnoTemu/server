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
    """API endpoint to get a story's cover image"""
    # Try to get the S3 URL first
    success, result = StoryController.get_story_cover_presigned_url(story_id)
    
    if success:
        # Redirect to the S3 presigned URL
        return redirect(result)
    
    # Fall back to local file if no S3 image (for backward compatibility)
    cover_path = StoryController.get_story_cover_path(story_id)
    
    if not cover_path:
        return jsonify({"error": "Cover image not found"}), 404
        
    # Get the file extension and determine the MIME type
    import mimetypes
    file_ext = cover_path.suffix.lower()
    content_type = mimetypes.guess_type(cover_path.name)[0]
    
    # Default to appropriate image type if not detected
    if not content_type:
        if file_ext == '.jpg' or file_ext == '.jpeg':
            content_type = 'image/jpeg'
        elif file_ext == '.png':
            content_type = 'image/png'
        elif file_ext == '.gif':
            content_type = 'image/gif'
        elif file_ext == '.webp':
            content_type = 'image/webp'
        elif file_ext == '.svg':
            content_type = 'image/svg+xml'
        else:
            content_type = 'application/octet-stream'
    
    # Convert Path object to string for Flask compatibility
    return send_from_directory(
        str(Config.STORIES_DIR),
        cover_path.name,
        mimetype=content_type
    )