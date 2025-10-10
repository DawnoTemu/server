"""
Audio synthesis tasks for StoryVoice.
This module contains Celery tasks for processing audio synthesis operations asynchronously.
"""

import logging
from celery import Task
from tasks import celery_app
from database import db

# Configure logger
logger = logging.getLogger('audio_tasks')

class AudioTask(Task):
    """Base task with error handling and app context management"""
    _flask_app = None
    
    @property
    def flask_app(self):
        if self._flask_app is None:
            from tasks import flask_app
            self._flask_app = flask_app
        return self._flask_app
    
    def __call__(self, *args, **kwargs):
        """Override Task.__call__ to ensure tasks run in an application context"""
        with self.flask_app.app_context():
            return self.run(*args, **kwargs)
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure by updating audio record status"""
        logger.error(f"Task {task_id} failed: {exc}")
        with self.flask_app.app_context():
            try:
                if args and args[0]:  # First argument should be audio_story_id
                    audio_id = args[0]
                    from models.audio_model import AudioStory, AudioStatus
                    from models.credit_model import refund_by_audio
                    audio = AudioStory.query.get(audio_id)
                    if audio:
                        audio.status = AudioStatus.ERROR.value
                        audio.error_message = str(exc)
                        db.session.commit()
                        logger.info(f"Updated audio {audio_id} status to ERROR")
                        # Refund credits for this audio attempt (idempotent)
                        try:
                            refund_by_audio(audio_id, reason="task_exception")
                            logger.info(f"Refunded credits for audio {audio_id} due to task failure")
                        except Exception as re:
                            logger.error(f"Failed to refund credits for audio {audio_id}: {re}")
            except Exception as e:
                logger.error(f"Error in on_failure handler: {e}")


@celery_app.task(bind=True, base=AudioTask, max_retries=2, 
                 autoretry_for=(Exception,), retry_backoff=True)
def synthesize_audio_task(self, audio_story_id, voice_id, story_id, text):
    """
    Asynchronous task to synthesize audio for a story
    
    Args:
        audio_story_id: ID of the audio story record
        voice_id: ID of the voice in our database
        story_id: ID of the story
        text: Text to synthesize
    
    Returns:
        bool: Success status
    """
    logger.info(f"Starting audio synthesis task for audio ID {audio_story_id}, voice {voice_id}, story {story_id}")
    
    try:
        # Import models here to avoid circular imports
        from models.audio_model import AudioStory, AudioModel, AudioStatus
        from models.voice_model import Voice, VoiceStatus
        
        # Get the audio story record
        audio_story = AudioStory.query.get(audio_story_id)
        if not audio_story:
            logger.error(f"Audio story record {audio_story_id} not found")
            return False
            
        # Verify voice is ready
        voice = Voice.query.get(voice_id)
        if not voice:
            logger.error(f"Voice {voice_id} not found")
            audio_story.status = AudioStatus.ERROR.value
            audio_story.error_message = "Voice not found"
            db.session.commit()
            # Refund on failure
            try:
                from models.credit_model import refund_by_audio
                refund_by_audio(audio_story_id, reason="voice_not_found")
            except Exception as re:
                logger.error(f"Refund failed for audio {audio_story_id}: {re}")
            return False
            
        if voice.status != VoiceStatus.READY:
            logger.error(f"Voice {voice_id} is not ready (status: {voice.status})")
            audio_story.status = AudioStatus.ERROR.value
            audio_story.error_message = f"Voice is not ready (status: {voice.status})"
            db.session.commit()
            try:
                from models.credit_model import refund_by_audio
                refund_by_audio(audio_story_id, reason="voice_not_ready")
            except Exception as re:
                logger.error(f"Refund failed for audio {audio_story_id}: {re}")
            return False
            
        if not voice.elevenlabs_voice_id:
            logger.error(f"Voice {voice_id} has no ElevenLabs ID")
            audio_story.status = AudioStatus.ERROR.value
            audio_story.error_message = "Voice has no ElevenLabs ID"
            db.session.commit()
            try:
                from models.credit_model import refund_by_audio
                refund_by_audio(audio_story_id, reason="missing_external_voice_id")
            except Exception as re:
                logger.error(f"Refund failed for audio {audio_story_id}: {re}")
            return False
            
        # Update status
        audio_story.status = AudioStatus.PROCESSING.value
        db.session.commit()
        
        # Synthesize speech
        synth_success, audio_data = AudioModel.synthesize_speech(voice.elevenlabs_voice_id, text)
        
        if not synth_success:
            logger.error(f"Speech synthesis failed: {audio_data}")
            audio_story.status = AudioStatus.ERROR.value
            audio_story.error_message = str(audio_data)
            db.session.commit()
            try:
                from models.credit_model import refund_by_audio
                refund_by_audio(audio_story_id, reason="synthesis_failed")
            except Exception as re:
                logger.error(f"Refund failed for audio {audio_story_id}: {re}")
            return False
            
        # Store audio
        store_success, message = AudioModel.store_audio(audio_data, voice_id, story_id, audio_story)
        
        if not store_success:
            logger.error(f"Audio storage failed: {message}")
            audio_story.status = AudioStatus.ERROR.value
            audio_story.error_message = message
            db.session.commit()
            try:
                from models.credit_model import refund_by_audio
                refund_by_audio(audio_story_id, reason="storage_failed")
            except Exception as re:
                logger.error(f"Refund failed for audio {audio_story_id}: {re}")
            return False
            
        logger.info(f"Audio synthesis successful for audio ID {audio_story_id}")
        return True
    
    except Exception as e:
        logger.exception(f"Exception in synthesize_audio_task: {e}")
        raise  # Let the task retry mechanism handle it
