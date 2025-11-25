"""
Voice recording post-processing tasks for StoryVoice.
This module contains Celery tasks for handling audio hygiene and metadata updates.
"""

import logging
import sentry_sdk
import random
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict
from io import BytesIO
from celery import Task
from tasks import celery_app
from database import db
from config import Config
from sqlalchemy import or_
from utils.voice_slot_queue import VoiceSlotQueue
from utils.metrics import emit_metric

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

        emit_metric("voice.process.dispatch_allocation", provider=str(voice.service_provider))

        logger.info("Enqueued allocation task %s for voice %s", allocation_task.id, voice_id)
        return True

    except Exception as e:
        logger.exception("Exception in process_voice_recording: %s", e)
        raise


@celery_app.task(
    bind=True,
    base=VoiceTask,
    name='voice.process_voice_queue',
)
def process_voice_queue(self):
    """Attempt to process queued allocation requests based on capacity."""
    from models.voice_model import Voice, VoiceModel, VoiceServiceProvider

    processed = 0
    dispatched_per_provider = defaultdict(int)
    requeued_in_cycle: set[int] = set()

    while True:
        request = VoiceSlotQueue.dequeue()
        if not request:
            break

        voice_id = request.get('voice_id')
        provider = request.get('service_provider')
        if provider is None and voice_id is not None:
            voice = Voice.query.get(voice_id)
            if voice:
                provider = voice.service_provider
                request['service_provider'] = provider

        if provider is None:
            provider = VoiceServiceProvider.ELEVENLABS

        capacity = VoiceModel.available_slot_capacity(provider)
        already_dispatched = dispatched_per_provider[provider]
        remaining_capacity = float('inf') if capacity == float('inf') else max(0, capacity - already_dispatched)

        if remaining_capacity <= 0:
            base_delay = max(int(getattr(Config, "VOICE_QUEUE_POLL_INTERVAL", 30) or 30) // 2, 5)
            jitter = random.randint(-base_delay // 3, base_delay // 3)
            delay_seconds = max(5, base_delay + jitter)
            VoiceSlotQueue.enqueue(voice_id, request, delay_seconds=delay_seconds)
            logger.debug(
                "Deferring voice %s due to slot capacity for provider %s",
                voice_id,
                provider,
            )
            if voice_id is not None:
                requeued_in_cycle.add(voice_id)
                if len(requeued_in_cycle) > 10:
                    break
            continue

        emit_metric("voice.queue.dispatch", provider=str(provider))
        allocate_voice_slot.delay(from_queue=True, **request)
        dispatched_per_provider[provider] += 1
        processed += 1

    if processed:
        logger.info("Dispatched %s queued allocation request(s)", processed)
        emit_metric("voice.queue.processed", processed)
    return processed


@celery_app.task(
    bind=True,
    base=VoiceTask,
    name='voice.reclaim_idle_voices',
)
def reclaim_idle_voices(self, max_to_reclaim: Optional[int] = None):
    """Release idle voices to free slots for queued requests."""
    from models.voice_model import (
        Voice,
        VoiceAllocationStatus,
        VoiceSlotEvent,
        VoiceSlotEventType,
        VoiceStatus,
    )
    from utils.voice_service import VoiceService

    queue_length = VoiceSlotQueue.length()
    if queue_length == 0:
        return 0

    now = datetime.utcnow()
    warm_hold_seconds = getattr(Config, "VOICE_WARM_HOLD_SECONDS", 900) or 0
    threshold = now - timedelta(seconds=warm_hold_seconds) if warm_hold_seconds > 0 else now

    limit = min(queue_length, max_to_reclaim) if max_to_reclaim else queue_length

    candidates = (
        Voice.query.filter(Voice.allocation_status == VoiceAllocationStatus.READY)
        .filter(or_(Voice.last_used_at.is_(None), Voice.last_used_at <= threshold))
        .filter(or_(Voice.slot_lock_expires_at.is_(None), Voice.slot_lock_expires_at <= now))
        .order_by(Voice.last_used_at.asc())
        .limit(limit)
        .all()
    )

    if not candidates:
        return 0

    reclaimed = 0
    for voice in candidates:
        try:
            if voice.elevenlabs_voice_id:
                success, message = VoiceService.delete_voice(
                    voice_id=voice.id,
                    external_voice_id=voice.elevenlabs_voice_id,
                    service=voice.service_provider,
                )
                if not success:
                    logger.error(
                        "Failed to delete remote voice %s during reclaim: %s",
                        voice.id,
                        message,
                    )
                    continue
        except Exception as exc:
            logger.error("Failed to release remote voice %s: %s", voice.id, exc)
            continue

        voice.status = VoiceStatus.RECORDED
        voice.allocation_status = VoiceAllocationStatus.RECORDED
        voice.elevenlabs_voice_id = None
        voice.elevenlabs_allocated_at = None
        voice.slot_lock_expires_at = None
        voice.last_used_at = now
        VoiceSlotEvent.log_event(
            voice_id=voice.id,
            user_id=voice.user_id,
            event_type=VoiceSlotEventType.SLOT_EVICTED,
            reason="idle_reclaim",
            metadata={'queue_size': queue_length},
        )
        reclaimed += 1

    if reclaimed:
        db.session.commit()
        process_voice_queue.delay()
        logger.info("Reclaimed %s idle voices", reclaimed)
    return reclaimed


_existing_schedule = getattr(celery_app.conf, 'beat_schedule', None) or {}
celery_app.conf.beat_schedule = {
    **_existing_schedule,
    'voice-process-queue': {
        'task': 'voice.process_voice_queue',
        'schedule': timedelta(seconds=getattr(Config, "VOICE_QUEUE_POLL_INTERVAL", 60) or 60),
    },
    'voice-reclaim-idle': {
        'task': 'voice.reclaim_idle_voices',
        'schedule': timedelta(minutes=5),
    },
}


@celery_app.task(
    bind=True,
    base=VoiceTask,
    max_retries=2,
    autoretry_for=(Exception,),
    retry_backoff=True,
    name='voice.allocate_voice_slot',
)
def allocate_voice_slot(self, voice_id, s3_key, filename, user_id, voice_name=None, *, attempts=0, from_queue=False, service_provider=None):
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

        provider = service_provider or voice.service_provider

        slot_capacity = VoiceModel.available_slot_capacity(provider)
        payload = {
            'voice_id': voice_id,
            's3_key': s3_key,
            'filename': filename,
            'user_id': user_id,
            'voice_name': voice_name,
            'attempts': attempts,
            'service_provider': provider,
        }

        if slot_capacity != float('inf') and slot_capacity <= 0 and voice.allocation_status != VoiceAllocationStatus.READY:
            delay_seconds = max(getattr(Config, "VOICE_QUEUE_POLL_INTERVAL", 30), 5 if from_queue else 0)
            VoiceSlotQueue.enqueue(voice_id, {**payload, 'attempts': attempts + 1}, delay_seconds=delay_seconds)
            VoiceSlotEvent.log_event(
                voice_id=voice.id,
                user_id=user_id,
                event_type=VoiceSlotEventType.ALLOCATION_QUEUED,
                reason="slot_limit_reached",
                metadata={'attempts': attempts + 1, 'queue_size': VoiceSlotQueue.length()},
            )
            voice.status = VoiceStatus.RECORDED
            voice.allocation_status = VoiceAllocationStatus.RECORDED
            db.session.commit()
            if not from_queue:
                countdown = getattr(Config, "VOICE_QUEUE_POLL_INTERVAL", 30) or 30
                process_voice_queue.apply_async(countdown=countdown)
            return {"queued": True}

        voice.status = VoiceStatus.PROCESSING
        voice.allocation_status = VoiceAllocationStatus.ALLOCATING
        VoiceSlotEvent.log_event(
            voice_id=voice.id,
            user_id=user_id,
            event_type=VoiceSlotEventType.ALLOCATION_STARTED,
            reason="allocate_voice_slot_task",
            metadata={'s3_key': s3_key, 'filename': filename, 'attempts': attempts},
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

        success, result = VoiceModel._clone_voice_api(
            file_data,
            filename,
            user_id,
            voice_name,
            service_provider=provider,
        )

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
            # Persist the provider used for this allocation to keep capacity accounting consistent
            voice.service_provider = provider
            voice.elevenlabs_allocated_at = datetime.utcnow()
            voice.last_used_at = datetime.utcnow()
            VoiceSlotQueue.remove(voice.id)

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
            process_voice_queue.delay()
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
