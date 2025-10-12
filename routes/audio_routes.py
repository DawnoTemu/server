from flask import request, jsonify, Response, redirect
from routes import audio_bp
from controllers.audio_controller import AudioController
from models.voice_model import VoiceModel
from utils.auth_middleware import token_required
import logging

# Configure logger
logger = logging.getLogger('audio_routes')


def _resolve_voice_for_user(voice_identifier: str, current_user):
    """Resolve a voice by external ElevenLabs ID first, then internal numeric ID."""
    voice = VoiceModel.get_voice_by_elevenlabs_id(voice_identifier)
    if not voice:
        try:
            numeric_id = int(voice_identifier)
        except (TypeError, ValueError):
            numeric_id = None
        if numeric_id is not None:
            voice = VoiceModel.get_voice_by_id(numeric_id)
    if not voice:
        return None, (jsonify({"error": "Voice not found"}), 404)
    if voice.user_id != current_user.id:
        return None, (jsonify({"error": "Unauthorized"}), 403)
    return voice, None


# GET /voices/:voice_id/stories/:story_id/audio - Stream or redirect to audio
@audio_bp.route('/voices/<string:voice_id>/stories/<int:story_id>/audio', methods=['GET'])
@token_required
def get_audio(current_user, voice_id, story_id):
    """Get synthesized audio for a voice and story combination"""
    try:
        voice, error_response = _resolve_voice_for_user(voice_id, current_user)
        if error_response:
            return error_response
        
        # Support both streaming and redirection via URL
        if 'redirect' in request.args:
            success, result, status_code = AudioController.get_audio_presigned_url(
                voice.id, 
                story_id,
                expires_in=int(request.args.get('expires', 3600))
            )
            
            if success:
                return redirect(result)
            return jsonify({"error": "Audio not found"}), 404
        
        # Stream audio with range support
        range_header = request.headers.get('Range')
        success, data, status_code, extra = AudioController.get_audio(voice.id, story_id, range_header)
        
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
        voice, error_response = _resolve_voice_for_user(voice_id, current_user)
        if error_response:
            # Preserve empty body semantics for HEAD responses
            return "", error_response[1]
        
        success, result, status_code = AudioController.check_audio_exists(voice.id, story_id)
        if not success:
            return "", status_code
        return "", 200 if result.get('exists') else 404
    except Exception as e:
        logger.error(f"Error in check_audio_exists route: {str(e)}")
        return "", 404

# POST /voices/:voice_id/stories/:story_id/audio - Generate new audio
@audio_bp.route('/voices/<string:voice_id>/stories/<int:story_id>/audio', methods=['POST'])
@token_required
def synthesize_audio(current_user, voice_id, story_id):
    """Generate new audio synthesis for a voice and story"""
    try:
        voice, error_response = _resolve_voice_for_user(voice_id, current_user)
        if error_response:
            return error_response
        
        success, result, status_code = AudioController.synthesize_audio(voice.id, story_id)
        response = jsonify(result)
        headers = {}
        voice_meta = result.get('voice') if isinstance(result, dict) else None
        if isinstance(voice_meta, dict):
            if 'queue_position' in voice_meta:
                headers['X-Voice-Queue-Position'] = str(voice_meta['queue_position'])
            if 'queue_length' in voice_meta:
                headers['X-Voice-Queue-Length'] = str(voice_meta['queue_length'])
            if 'elevenlabs_voice_id' in voice_meta:
                headers['X-Voice-Remote-ID'] = str(voice_meta['elevenlabs_voice_id'])
        return (response, status_code, headers) if headers else (response, status_code)
    except Exception as e:
        logger.error(f"Error in synthesize_audio route: {str(e)}")
        return jsonify({"error": f"Failed to synthesize audio: {str(e)}"}), 500
