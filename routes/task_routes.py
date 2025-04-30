"""
Routes for checking task status and retrieving results for async operations.
"""

from flask import jsonify
from routes import task_bp
from utils.auth_middleware import token_required
from models.voice_model import Voice, VoiceStatus 
from models.audio_model import AudioStory, AudioStatus

@task_bp.route('/voices/<int:voice_id>/status', methods=['GET'])
@token_required
def get_voice_status(current_user, voice_id):
    """Get the status of a voice cloning operation
    
    Args:
        voice_id: ID of the voice
        
    Returns:
        JSON response with status information
    """
    # Get the voice
    voice = Voice.query.get(voice_id)
    
    if not voice:
        return jsonify({"error": "Voice not found"}), 404
    
    # Check ownership
    if voice.user_id != current_user.id:
        return jsonify({"error": "Unauthorized"}), 403
    
    # Return voice status
    result = {
        "id": voice.id,
        "status": voice.status,
        "created_at": voice.created_at.isoformat() if voice.created_at else None,
        "updated_at": voice.updated_at.isoformat() if voice.updated_at else None,
    }
    
    # Add error message if there was one
    if voice.status == VoiceStatus.ERROR and voice.error_message:
        result["error"] = voice.error_message
    
    # Add voice ID if ready
    if voice.status == VoiceStatus.READY and voice.elevenlabs_voice_id:
        result["elevenlabs_voice_id"] = voice.elevenlabs_voice_id
    
    return jsonify(result), 200

@task_bp.route('/audio/<int:audio_id>/status', methods=['GET'])
@token_required
def get_audio_status(current_user, audio_id):
    """Get the status of an audio synthesis operation
    
    Args:
        audio_id: ID of the audio story
        
    Returns:
        JSON response with status information
    """
    # Get the audio story
    audio = AudioStory.query.get(audio_id)
    
    if not audio:
        return jsonify({"error": "Audio not found"}), 404
    
    # Check ownership
    if audio.user_id != current_user.id:
        return jsonify({"error": "Unauthorized"}), 403
    
    # Return audio status
    result = {
        "id": audio.id,
        "status": audio.status,
        "story_id": audio.story_id,
        "voice_id": audio.voice_id,
        "created_at": audio.created_at.isoformat() if audio.created_at else None,
        "updated_at": audio.updated_at.isoformat() if audio.updated_at else None,
    }
    
    # Add error message if there was one
    if audio.status == AudioStatus.ERROR.value and audio.error_message:
        result["error"] = audio.error_message
    
    # Add URL if ready
    if audio.status == AudioStatus.READY.value and audio.s3_key:
        from models.audio_model import AudioModel
        success, url = AudioModel.get_audio_presigned_url(audio.voice_id, audio.story_id)
        if success:
            result["url"] = url
    
    return jsonify(result), 200