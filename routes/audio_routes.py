from flask import request, jsonify, Response, redirect
from routes import audio_bp
from controllers.audio_controller import AudioController
from models.voice_model import VoiceModel, Voice 
from utils.auth_middleware import token_required
import logging

# Configure logger
logger = logging.getLogger('audio_routes')

# GET /voices/:voice_id/stories/:story_id/audio - Stream or redirect to audio
@audio_bp.route('/voices/<string:voice_id>/stories/<int:story_id>/audio', methods=['GET'])
@token_required
def get_audio(current_user, voice_id, story_id):
    """Get synthesized audio for a voice and story combination"""
    try:
        # Verify ownership
        voice = VoiceModel.get_voice_by_elevenlabs_id(voice_id)
        if voice and voice.user_id != current_user.id:
            return jsonify({"error": "Unauthorized"}), 403
        
        # Support both streaming and redirection via URL
        if 'redirect' in request.args:
            success, result, status_code = AudioController.get_audio_presigned_url(
                voice_id, 
                story_id,
                expires_in=int(request.args.get('expires', 3600))
            )
            
            if success:
                return redirect(result)
            return jsonify({"error": "Audio not found"}), 404
        
        # Stream audio with range support
        range_header = request.headers.get('Range')
        success, data, status_code, extra = AudioController.get_audio(voice_id, story_id, range_header)
        
        if not success:
            return jsonify(data), status_code
        
        # Create response with appropriate headers
        response = Response(data, status=status_code, mimetype='audio/mpeg')
        response.headers['Accept-Ranges'] = 'bytes'
        
        if extra:
            if 'content_length' in extra:
                response.headers['Content-Length'] = str(extra['content_length'])
            if 'content_range' in extra:
                response.headers['Content-Range'] = extra['content_range']
        
        return response
    except Exception as e:
        logger.error(f"Error in get_audio route: {str(e)}")
        return jsonify({"error": "Failed to retrieve audio"}), 500

# HEAD /voices/:voice_id/stories/:story_id/audio - Check if audio exists
@audio_bp.route('/voices/<string:voice_id>/stories/<int:story_id>/audio', methods=['HEAD'])
@token_required
def check_audio_exists(current_user, voice_id, story_id):
    """Check if audio exists without transferring the file"""
    try:
        # Verify ownership
        voice = VoiceModel.get_voice_by_elevenlabs_id(voice_id)
        if voice and voice.user_id != current_user.id:
            return "", 403
        
        # Check if audio exists
        exists = AudioModel.check_audio_exists(voice_id, story_id)
        
        return "", 200 if exists else 404
    except Exception as e:
        logger.error(f"Error in check_audio_exists route: {str(e)}")
        return "", 404

# POST /voices/:voice_id/stories/:story_id/audio - Generate new audio
@audio_bp.route('/voices/<string:voice_id>/stories/<int:story_id>/audio', methods=['POST'])
@token_required
def synthesize_audio(current_user, voice_id, story_id):
    """Generate new audio synthesis for a voice and story"""
    try:
        # Verify ownership
        voice = VoiceModel.get_voice_by_elevenlabs_id(voice_id)
        
        if not voice:
            return jsonify({"error": "Voice not found"}), 404
            
        if voice.user_id != current_user.id:
            return jsonify({"error": "Unauthorized"}), 403
        
        success, result, status_code = AudioController.synthesize_audio(voice_id, story_id)
        return jsonify(result), status_code
    except Exception as e:
        logger.error(f"Error in synthesize_audio route: {str(e)}")
        return jsonify({"error": f"Failed to synthesize audio: {str(e)}"}), 500