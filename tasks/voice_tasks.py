"""
Voice recording post-processing tasks for StoryVoice.
This module contains Celery tasks for handling audio hygiene and metadata updates.
"""

import logging
import sentry_sdk
from datetime import datetime
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
        # Capture the exception in Sentry
        sentry_sdk.capture_exception(exc)
        with self.flask_app.app_context():
            try:
                if args and args[0]:  # First argument should be voice_id
                    voice_id = args[0]
                    from models.voice_model import (
                        Voice,
                        VoiceStatus,
                        VoiceAllocationStatus,
                        VoiceSlotEvent,
                        VoiceSlotEventType,
                    )
                    voice = Voice.query.get(voice_id)
                    if voice:
                        voice.status = VoiceStatus.ERROR
                        voice.allocation_status = VoiceAllocationStatus.RECORDED
                        voice.error_message = str(exc)
                        VoiceSlotEvent.log_event(
                            voice_id=voice.id,
                            user_id=voice.user_id,
                            event_type=VoiceSlotEventType.ALLOCATION_FAILED
                            if self.name == 'voice.allocate_voice_slot'
                            else VoiceSlotEventType.RECORDING_PROCESSING_FAILED,
                            reason="allocate_voice_slot_failure" if self.name == 'voice.allocate_voice_slot' else "process_voice_recording_failure",
                            metadata={'error': str(exc)},
                        )
                        db.session.commit()
                        logger.info(f"Updated voice {voice_id} status to ERROR")
            except Exception as e:
                logger.error(f"Error in on_failure handler: {e}")


@celery_app.task(
    bind=True,
    base=VoiceTask,
    max_retries=1,
    autoretry_for=(Exception,),
    retry_backoff=True,
    name='voice.process_voice_recording',
)
def process_voice_recording(self, voice_id, s3_key, filename, user_id, voice_name=None):
    """
    Asynchronous task to perform lightweight processing on uploaded recordings.

    Args:
        voice_id: ID of the voice record in the database
        s3_key: Permanent S3 key where the audio file is stored
        filename: Original filename
        user_id: ID of the user who owns this voice
        voice_name: Optional name for the voice

    Returns:
        bool: Success status
    """
    logger.info("Processing voice recording %s (voice_id=%s)", s3_key, voice_id)

    try:
        from models.voice_model import (
            Voice,
            VoiceSlotEvent,
            VoiceSlotEventType,
            VoiceStatus,
        )
        from utils.s3_client import S3Client

        voice = Voice.query.get(voice_id)
        if not voice:
            logger.error("Voice record %s not found during processing", voice_id)
            return False

        # Capture current metadata from S3 (size, encryption, storage class, etc.)
        head_metadata = {}
        try:
            head_obj = S3Client.get_client().head_object(
                Bucket=S3Client.get_bucket_name(),
                Key=s3_key,
            )
            head_metadata = {
                'filesize': head_obj.get('ContentLength'),
                'encryption': head_obj.get('ServerSideEncryption'),
                'storage_class': head_obj.get('StorageClass'),
                'content_type': head_obj.get('ContentType'),
            }
            if head_metadata['filesize'] is not None:
                voice.recording_filesize = int(head_metadata['filesize'])
        except Exception as e:
            logger.warning("Failed to inspect S3 metadata for %s: %s", s3_key, e)
            head_metadata['inspection_error'] = str(e)

        # Ensure voice remains in recorded state
        voice.status = VoiceStatus.RECORDED
        voice.updated_at = datetime.utcnow()

        VoiceSlotEvent.log_event(
            voice_id=voice.id,
            user_id=user_id,
            event_type=VoiceSlotEventType.RECORDING_PROCESSED,
            reason="post_upload_metadata_refresh",
            metadata={
                'filename': filename,
                's3_key': s3_key,
                **{k: v for k, v in head_metadata.items() if v is not None},
            },
        )
        db.session.commit()

        logger.info("Completed processing for voice %s", voice_id)

        allocation_task = allocate_voice_slot.delay(
            voice_id=voice_id,
            s3_key=voice.recording_s3_key,
            filename=filename,
            user_id=user_id,
            voice_name=voice_name,
        )

        VoiceSlotEvent.log_event(
            voice_id=voice.id,
            user_id=user_id,
            event_type=VoiceSlotEventType.ALLOCATION_STARTED,
            reason="automatic_slot_allocation",
            metadata={
                'task_id': allocation_task.id,
                's3_key': voice.recording_s3_key,
            },
        )
        db.session.commit()

        logger.info("Enqueued allocation task %s for voice %s", allocation_task.id, voice_id)
        return True

    except Exception as e:
        logger.exception("Exception in process_voice_recording: %s", e)
        raise


@celery_app.task(
    bind=True,
    base=VoiceTask,
    max_retries=2,
    autoretry_for=(Exception,),
    retry_backoff=True,
    name='voice.allocate_voice_slot',
)
def allocate_voice_slot(self, voice_id, s3_key, filename, user_id, voice_name=None):
    """Allocate an external voice slot (e.g., ElevenLabs) for an uploaded recording."""
    logger.info("Allocating voice slot for voice_id=%s", voice_id)

    try:
        from models.voice_model import (
            Voice,
            VoiceAllocationStatus,
            VoiceModel,
            VoiceSlotEvent,
            VoiceSlotEventType,
            VoiceStatus,
        )
        from utils.s3_client import S3Client

        voice = Voice.query.get(voice_id)
        if not voice:
            logger.error("Voice record %s not found during allocation", voice_id)
            return False

        voice.status = VoiceStatus.PROCESSING
        voice.allocation_status = VoiceAllocationStatus.ALLOCATING
        VoiceSlotEvent.log_event(
            voice_id=voice.id,
            user_id=user_id,
            event_type=VoiceSlotEventType.ALLOCATION_STARTED,
            reason="allocate_voice_slot_task",
            metadata={'s3_key': s3_key, 'filename': filename},
        )
        db.session.commit()

        try:
            file_obj = S3Client.download_fileobj(s3_key)
            file_data = BytesIO(file_obj.read())
        except Exception as e:
            logger.error("Failed to download recording for allocation: %s", e)
            voice.status = VoiceStatus.ERROR
            voice.allocation_status = VoiceAllocationStatus.RECORDED
            voice.error_message = f"Could not download recording: {e}"
            VoiceSlotEvent.log_event(
                voice_id=voice.id,
                user_id=user_id,
                event_type=VoiceSlotEventType.ALLOCATION_FAILED,
                reason="download_failed",
                metadata={'error': str(e)},
            )
            db.session.commit()
            return False

        success, result = VoiceModel._clone_voice_api(file_data, filename, user_id, voice_name)

        if success:
            external_voice_id = result.get("voice_id")
            if not external_voice_id:
                voice.status = VoiceStatus.ERROR
                voice.allocation_status = VoiceAllocationStatus.RECORDED
                voice.error_message = "No voice ID returned from voice service"
                VoiceSlotEvent.log_event(
                    voice_id=voice.id,
                    user_id=user_id,
                    event_type=VoiceSlotEventType.ALLOCATION_FAILED,
                    reason="missing_external_id",
                )
                db.session.commit()
                return False

            voice.elevenlabs_voice_id = external_voice_id
            voice.status = VoiceStatus.READY
            voice.allocation_status = VoiceAllocationStatus.READY
            voice.service_provider = VoiceModel._resolve_service_provider()
            voice.elevenlabs_allocated_at = datetime.utcnow()
            voice.last_used_at = datetime.utcnow()

            VoiceSlotEvent.log_event(
                voice_id=voice.id,
                user_id=user_id,
                event_type=VoiceSlotEventType.ALLOCATION_COMPLETED,
                reason="voice_ready",
                metadata={
                    'external_voice_id': external_voice_id,
                    's3_key': s3_key,
                },
            )
            db.session.commit()
            logger.info("Voice %s allocated with external ID %s", voice_id, external_voice_id)
            return True

        voice.status = VoiceStatus.ERROR
        voice.allocation_status = VoiceAllocationStatus.RECORDED
        voice.error_message = str(result)
        VoiceSlotEvent.log_event(
            voice_id=voice.id,
            user_id=user_id,
            event_type=VoiceSlotEventType.ALLOCATION_FAILED,
            reason="voice_service_error",
            metadata={'error': str(result)},
        )
        db.session.commit()
        logger.error("Voice allocation failed for voice_id=%s: %s", voice_id, result)
        return False

    except Exception as e:
        logger.exception("Exception in allocate_voice_slot: %s", e)
        try:
            from models.voice_model import (
                Voice,
                VoiceAllocationStatus,
                VoiceSlotEvent,
                VoiceSlotEventType,
                VoiceStatus,
            )
            voice = Voice.query.get(voice_id)
            if voice:
                voice.status = VoiceStatus.ERROR
                voice.allocation_status = VoiceAllocationStatus.RECORDED
                voice.error_message = str(e)
                VoiceSlotEvent.log_event(
                    voice_id=voice.id,
                    user_id=user_id,
                    event_type=VoiceSlotEventType.ALLOCATION_FAILED,
                    reason="allocate_voice_slot_exception",
                    metadata={'error': str(e)},
                )
                db.session.commit()
        except Exception as inner_exc:
            logger.error("Failed to record allocation failure for voice %s: %s", voice_id, inner_exc)
            db.session.rollback()
        raise
