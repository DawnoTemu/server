from flask import request, jsonify, Response, redirect
from routes import audio_bp
from controllers.audio_controller import AudioController

@audio_bp.route('/audio/url/<string:voice_id>/<int:story_id>')
def get_audio_url(voice_id, story_id):
    """API endpoint to get a presigned URL for direct S3 access"""
    # Get expiration time from query params (default: 1 hour)
    expires_in = int(request.args.get('expires', 3600))
    
    success, result, status_code = AudioController.get_audio_presigned_url(
        voice_id, 
        story_id,
        expires_in=expires_in
    )
    
    return jsonify(result), status_code

@audio_bp.route('/audio/exists/<string:voice_id>/<int:story_id>')
def check_audio_exists(voice_id, story_id):
    """API endpoint to check if audio exists"""
    success, result, status_code = AudioController.check_audio_exists(voice_id, story_id)
    
    return jsonify(result), status_code

@audio_bp.route('/synthesize', methods=['POST'])
def synthesize_speech():
    """API endpoint to synthesize speech"""
    data = request.json
    
    # Validate request data
    if not (voice_id := data.get('voice_id')):
        return jsonify({"error": "Missing voice_id"}), 400
        
    if not (story_id := data.get('story_id')):
        return jsonify({"error": "Missing story_id"}), 400
    
    success, result, status_code = AudioController.synthesize_audio(voice_id, story_id)
    
    return jsonify(result), status_code