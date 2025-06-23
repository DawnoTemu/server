"""
Voice cloning tasks for StoryVoice.
This module contains Celery tasks for processing voice cloning operations asynchronously.
"""

import os
import logging
from io import BytesIO
from celery import Task
from tasks import celery_app
from database import db

# Configure logger
logger = logging.getLogger('voice_tasks')

class VoiceTask(Task):
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
        """Handle task failure by updating voice record status"""
        logger.error(f"Task {task_id} failed: {exc}")
        with self.flask_app.app_context():
            try:
                if args and args[0]:  # First argument should be voice_id
                    voice_id = args[0]
                    from models.voice_model import Voice, VoiceStatus
                    voice = Voice.query.get(voice_id)
                    if voice:
                        voice.status = VoiceStatus.ERROR
                        voice.error_message = str(exc)
                        db.session.commit()
                        logger.info(f"Updated voice {voice_id} status to ERROR")
            except Exception as e:
                logger.error(f"Error in on_failure handler: {e}")


@celery_app.task(bind=True, base=VoiceTask, max_retries=2, 
                 autoretry_for=(Exception,), retry_backoff=True)
def clone_voice_task(self, voice_id, s3_key, filename, user_id, voice_name=None):
    """
    Asynchronous task to clone a voice using voice synthesis APIs
    
    Args:
        voice_id: ID of the voice record in the database
        s3_key: S3 key where the audio file is temporarily stored
        filename: Original filename
        user_id: ID of the user who owns this voice
        voice_name: Optional name for the voice
        
    Returns:
        bool: Success status
    """
    logger.info(f"Starting voice cloning task for voice ID {voice_id}")
    
    try:
        # Import models here to avoid circular imports
        from models.voice_model import Voice, VoiceModel, VoiceStatus
        from utils.s3_client import S3Client
        
        # Get the voice record
        voice = Voice.query.get(voice_id)
        if not voice:
            logger.error(f"Voice record {voice_id} not found")
            return False
            
        # Update status to processing
        voice.status = VoiceStatus.PROCESSING
        db.session.commit()
        
        # Download file data from S3
        try:
            logger.info(f"Downloading file from S3: {s3_key}")
            file_obj = S3Client.download_fileobj(s3_key)
            file_data = BytesIO(file_obj.read())
            logger.info(f"Successfully downloaded file from S3, size: {len(file_data.getvalue())} bytes")
        except Exception as e:
            logger.error(f"Error downloading file from S3 {s3_key}: {e}")
            voice.status = VoiceStatus.ERROR
            voice.error_message = f"Could not download voice sample from S3: {str(e)}"
            db.session.commit()
            return False
            
        # Call API to clone voice
        success, result = VoiceModel._clone_voice_api(file_data, filename, user_id, voice_name)
        
        if success:
            # Get the voice ID from the result
            external_voice_id = result.get("voice_id")
            
            if not external_voice_id:
                voice.status = VoiceStatus.ERROR
                voice.error_message = "No voice ID returned from voice service"
                db.session.commit()
                return False
                
            # Store original sample in S3 (permanent location)
            permanent_s3_key = None
            try:
                # Reset file position
                file_data.seek(0)
                
                # Generate permanent S3 key for the sample
                permanent_s3_key = f"{VoiceModel.VOICE_SAMPLES_PREFIX}{user_id}/{external_voice_id}.mp3"
                
                # Upload to permanent S3 location
                extra_args = {
                    'ContentType': 'audio/mpeg',
                    'CacheControl': 'max-age=31536000',  # Cache for 1 year
                }
                
                S3Client.upload_fileobj(file_data, permanent_s3_key, extra_args)
                logger.info(f"Stored voice sample in permanent S3 location: {permanent_s3_key}")
            except Exception as e:
                logger.error(f"Failed to store voice sample in permanent S3 location: {str(e)}")
                # Continue even if permanent S3 storage fails
            
            # Update voice record with successful results
            voice.elevenlabs_voice_id = external_voice_id
            voice.s3_sample_key = permanent_s3_key
            voice.sample_filename = filename
            voice.status = VoiceStatus.READY
            db.session.commit()
            
            logger.info(f"Voice cloning successful for voice ID {voice_id}, External Voice ID: {external_voice_id}")
            return True
        else:
            # Update with error
            voice.status = VoiceStatus.ERROR
            voice.error_message = str(result)
            db.session.commit()
            logger.error(f"Voice cloning failed for voice ID {voice_id}: {result}")
            return False
    
    except Exception as e:
        logger.exception(f"Exception in clone_voice_task: {e}")
        raise  # Let the task retry mechanism handle it
        
    finally:
        # Clean up temporary S3 file
        try:
            from utils.s3_client import S3Client
            S3Client.delete_objects([s3_key])
            logger.info(f"Cleaned up temporary S3 file: {s3_key}")
        except Exception as e:
            logger.error(f"Failed to clean up temporary S3 file {s3_key}: {e}")