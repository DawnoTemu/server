from flask import jsonify, request
from routes import task_bp
from utils.auth_middleware import token_required
from models.voice_model import Voice, VoiceStatus 
from models.audio_model import AudioStory, AudioStatus
from celery.result import AsyncResult
from tasks import celery_app
import logging

logger = logging.getLogger('task_routes')

@task_bp.route('/voices/<int:voice_id>/status', methods=['GET'])
@token_required
def get_voice_status(current_user, voice_id):
    """Get the status of a voice cloning operation"""
    # Get the voice
    voice = Voice.query.get(voice_id)
    
    if not voice:
        return jsonify({"error": "Voice not found"}), 404
    
    # Check ownership
    if voice.user_id != current_user.id:
        return jsonify({"error": "Unauthorized"}), 403
    
    # Get task ID from request if available (for checking Celery status)
    task_id = request.args.get('task_id')
    celery_status = None
    
    if task_id:
        # Check Celery task status
        task_result = AsyncResult(task_id, app=celery_app)
        celery_status = {
            "state": task_result.state,
            "ready": task_result.ready(),
            "successful": task_result.successful() if task_result.ready() else None,
            "info": str(task_result.info) if task_result.info else None
        }
    
    # Return voice status
    result = {
        "id": voice.id,
        "name": voice.name,
        "status": voice.status,
        "created_at": voice.created_at.isoformat() if voice.created_at else None,
        "updated_at": voice.updated_at.isoformat() if voice.updated_at else None,
    }
    
    # Add task status if available
    if celery_status:
        result["task_status"] = celery_status
    
    # Add error message if there was one
    if voice.status == VoiceStatus.ERROR and voice.error_message:
        result["error"] = voice.error_message
    
    # Add voice ID if ready
    if voice.status == VoiceStatus.READY and voice.elevenlabs_voice_id:
        result["elevenlabs_voice_id"] = voice.elevenlabs_voice_id
        
        # Include sample URL if ready
        from models.voice_model import VoiceModel
        success, url = VoiceModel.get_sample_url(voice.id)
        if success:
            result["sample_url"] = url
    
    return jsonify(result), 200

@task_bp.route('/audio/<int:audio_id>/status', methods=['GET'])
@token_required
def get_audio_status(current_user, audio_id):
    """Get the status of an audio synthesis operation"""
    # Get the audio story
    audio = AudioStory.query.get(audio_id)
    
    if not audio:
        return jsonify({"error": "Audio not found"}), 404
    
    # Check ownership
    if audio.user_id != current_user.id:
        return jsonify({"error": "Unauthorized"}), 403
    
    # Get task ID from request if available
    task_id = request.args.get('task_id')
    celery_status = None
    
    if task_id:
        # Check Celery task status
        task_result = AsyncResult(task_id, app=celery_app)
        celery_status = {
            "state": task_result.state,
            "ready": task_result.ready(),
            "successful": task_result.successful() if task_result.ready() else None,
            "info": str(task_result.info) if task_result.info else None
        }
    
    # Return audio status
    result = {
        "id": audio.id,
        "status": audio.status,
        "story_id": audio.story_id,
        "voice_id": audio.voice_id,
        "created_at": audio.created_at.isoformat() if audio.created_at else None,
        "updated_at": audio.updated_at.isoformat() if audio.updated_at else None,
        "duration_seconds": audio.duration_seconds,
        "file_size_bytes": audio.file_size_bytes
    }
    
    # Add task status if available
    if celery_status:
        result["task_status"] = celery_status
    
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

@task_bp.route('/tasks/<task_id>', methods=['GET'])
@token_required
def get_task_status(current_user, task_id):
    """Get the status of any Celery task"""
    try:
        # Check Celery task status
        task_result = AsyncResult(task_id, app=celery_app)
        
        result = {
            "id": task_id,
            "state": task_result.state,
            "ready": task_result.ready(),
            "successful": task_result.successful() if task_result.ready() else None,
        }
        
        # Add result or error info if task is ready
        if task_result.ready():
            if task_result.successful():
                result["result"] = task_result.result
            else:
                result["error"] = str(task_result.result)
        
        # Add task info if available
        if task_result.info:
            result["info"] = str(task_result.info)
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error checking task status: {e}")
        return jsonify({"error": f"Error checking task status: {str(e)}"}), 500