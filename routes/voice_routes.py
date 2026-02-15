from flask import request, jsonify, redirect
from routes import voice_bp
from controllers.voice_controller import VoiceController
from utils.auth_middleware import token_required
from utils.rate_limiter import limiter

# GET /voices - List all voices for the authenticated user
@voice_bp.route('/voices', methods=['GET'])
@token_required
def list_voices(current_user):
    """List all voices belonging to the authenticated user"""
    success, result, status_code = VoiceController.get_voices_by_user(current_user.id)
    return jsonify(result), status_code

# POST /voices - Create a new voice
@voice_bp.route('/voices', methods=['POST'])
@limiter.limit("5 per minute")
@token_required
def create_voice(current_user):
    """Create a new voice clone from uploaded audio"""
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
        
    file = request.files['file']
    voice_name = request.form.get('name')
    
    success, result, status_code = VoiceController.clone_voice(
        file, 
        current_user.id,
        voice_name=voice_name
    )
    
    return jsonify(result), status_code

# GET /voices/:id - Get a specific voice
@voice_bp.route('/voices/<int:voice_id>', methods=['GET'])
@token_required
def get_voice(current_user, voice_id):
    """Get a specific voice by ID"""
    success, result, status_code = VoiceController.get_voice(voice_id)
    
    if success:
        # Verify ownership
        if result.get('user_id') != current_user.id:
            return jsonify({"error": "Unauthorized"}), 403
    
    return jsonify(result), status_code

# DELETE /voices/:id - Delete a voice
@voice_bp.route('/voices/<int:voice_id>', methods=['DELETE'])
@limiter.limit("10 per minute")
@token_required
def delete_voice(current_user, voice_id):
    """Delete a voice by ID"""
    # Verify ownership
    voice_check, voice_result, status_code = VoiceController.get_voice(voice_id)
    
    if not voice_check:
        return jsonify(voice_result), status_code
        
    if voice_result.get('user_id') != current_user.id:
        return jsonify({"error": "Unauthorized"}), 403
    
    success, result, status_code = VoiceController.delete_voice(voice_id)
    return jsonify(result), status_code

# GET /voices/:id/sample - Get a voice sample audio
@voice_bp.route('/voices/<int:voice_id>/sample', methods=['GET'])
@token_required
def get_voice_sample(current_user, voice_id):
    """Get the sample audio for a voice"""
    # Verify ownership
    voice_check, voice_result, status_code = VoiceController.get_voice(voice_id)
    
    if not voice_check:
        return jsonify(voice_result), status_code
        
    if voice_result.get('user_id') != current_user.id:
        return jsonify({"error": "Unauthorized"}), 403
    
    # Get the sample URL
    success, result, status_code = VoiceController.get_voice_sample_url(voice_id)
    
    if success and 'redirect' in request.args:
        return redirect(result['url'])
        
    return jsonify(result), status_code