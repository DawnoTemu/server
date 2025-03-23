from flask import request, jsonify, redirect
from routes import voice_bp
from controllers.voice_controller import VoiceController
from utils.auth_middleware import token_required

@voice_bp.route('/voices', methods=['GET'])
@token_required
def list_voices(current_user):
    """API endpoint to list all voices for the current user"""
    success, result, status_code = VoiceController.get_voices_by_user(current_user.id)
    
    return jsonify(result), status_code

@voice_bp.route('/voices/<int:voice_id>', methods=['GET'])
@token_required
def get_voice(current_user, voice_id):
    """API endpoint to get a specific voice"""
    success, result, status_code = VoiceController.get_voice(voice_id)
    
    if success:
        # Check if the voice belongs to the current user
        if result.get('user_id') != current_user.id:
            return jsonify({"error": "Unauthorized"}), 403
    
    return jsonify(result), status_code

@voice_bp.route('/voices/<int:voice_id>/sample', methods=['GET'])
@token_required
def get_voice_sample(current_user, voice_id):
    """API endpoint to get a voice sample audio URL"""
    # First check if the voice exists and belongs to the user
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

@voice_bp.route('/clone', methods=['POST'])
@token_required
def clone_voice(current_user):
    """API endpoint for voice cloning"""
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

@voice_bp.route('/voices/<int:voice_id>', methods=['DELETE'])
@token_required
def delete_voice(current_user, voice_id):
    """API endpoint for voice deletion"""
    # First check if the voice belongs to the current user
    voice_check, voice_result, status_code = VoiceController.get_voice(voice_id)
    
    if not voice_check:
        return jsonify(voice_result), status_code
        
    if voice_result.get('user_id') != current_user.id:
        return jsonify({"error": "Unauthorized"}), 403
    
    success, result, status_code = VoiceController.delete_voice(voice_id)
    
    return jsonify(result), status_code