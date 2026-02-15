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

        # Voice remains in RECORDED state. Remote slot allocation is deferred
        # until the first audio synthesis request (just-in-time allocation via
        # VoiceSlotManager.ensure_active_voice).
        emit_metric("voice.process.completed", provider=str(voice.service_provider))
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
    batch_size = getattr(Config, "VOICE_QUEUE_BATCH_SIZE", 20) or 20
    ready_items = VoiceSlotQueue.dequeue_ready_batch(batch_size)
    if not ready_items:
        return 0

    # Populate provider where missing (legacy payloads)
    for item in ready_items:
        if not item.get("service_provider"):
            voice_id = item.get("voice_id")
            provider = None
            if voice_id is not None:
                voice = Voice.query.get(voice_id)
                if voice:
                    provider = voice.service_provider
            item["service_provider"] = provider or VoiceServiceProvider.ELEVENLABS

    # Group by provider to apply per-provider capacity
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in ready_items:
        grouped[item["service_provider"]].append(item)

    for provider, items in grouped.items():
        capacity = VoiceModel.available_slot_capacity(provider)
        if capacity != float("inf"):
            capacity = max(int(capacity or 0), 0)

        if capacity == 0:
            base_delay = max(int(getattr(Config, "VOICE_QUEUE_POLL_INTERVAL", 30) or 30) // 2, 5)
            jitter = random.randint(-base_delay // 3, base_delay // 3)
            delay_seconds = max(5, base_delay + jitter)
            for item in items:
                VoiceSlotQueue.enqueue(item["voice_id"], item, delay_seconds=delay_seconds)
            continue

        to_dispatch = items if capacity == float("inf") else items[:capacity]
        for item in to_dispatch:
            emit_metric("voice.queue.dispatch", provider=str(provider))
            allocate_voice_slot.delay(from_queue=True, **item)
            processed += 1

        if capacity != float("inf") and len(items) > capacity:
            # Re-enqueue overflow with jitter to avoid immediate contention
            base_delay = max(int(getattr(Config, "VOICE_QUEUE_POLL_INTERVAL", 30) or 30) // 2, 5)
            for item in items[capacity:]:
                jitter = random.randint(-base_delay // 3, base_delay // 3)
                delay_seconds = max(5, base_delay + jitter)
                VoiceSlotQueue.enqueue(item["voice_id"], item, delay_seconds=delay_seconds)

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
    """Release idle voices to free slots for queued requests or proactive cleanup."""
    from models.voice_model import (
        Voice,
        VoiceAllocationStatus,
        VoiceSlotEvent,
        VoiceSlotEventType,
        VoiceStatus,
    )
    from utils.voice_service import VoiceService

    def _evict_voice(voice, reason: str, metadata: dict) -> bool:
        """Evict a single voice. Returns True on success."""
        try:
            if voice.elevenlabs_voice_id:
                success, message = VoiceService.delete_voice(
                    voice_id=voice.id,
                    external_voice_id=voice.elevenlabs_voice_id,
                    service=voice.service_provider,
                )
                if not success:
                    logger.error(
                        "Failed to delete remote voice %s during %s: %s",
                        voice.id, reason, message,
                    )
                    return False
        except Exception as exc:
            logger.error("Failed to release remote voice %s: %s", voice.id, exc)
            return False

        voice.status = VoiceStatus.RECORDED
        voice.allocation_status = VoiceAllocationStatus.RECORDED
        voice.elevenlabs_voice_id = None
        voice.elevenlabs_allocated_at = None
        voice.slot_lock_expires_at = None
        voice.last_used_at = datetime.utcnow()
        VoiceSlotEvent.log_event(
            voice_id=voice.id,
            user_id=voice.user_id,
            event_type=VoiceSlotEventType.SLOT_EVICTED,
            reason=reason,
            metadata=metadata,
        )
        return True

    now = datetime.utcnow()
    queue_length = VoiceSlotQueue.length()
    reclaimed = 0

    # Fast path: reclaim for queue pressure (uses warm-hold threshold)
    if queue_length > 0:
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

        for voice in candidates:
            if _evict_voice(voice, "idle_reclaim", {'queue_size': queue_length}):
                reclaimed += 1

    # Slow path: proactive cleanup of very stale voices (even when queue is empty)
    max_idle_hours = getattr(Config, "VOICE_MAX_IDLE_HOURS", 24) or 0
    if max_idle_hours > 0:
        stale_threshold = now - timedelta(hours=max_idle_hours)
        # Limit proactive cleanup to avoid long-running task
        proactive_limit = 5

        stale_candidates = (
            Voice.query.filter(Voice.allocation_status == VoiceAllocationStatus.READY)
            .filter(Voice.last_used_at <= stale_threshold)
            .filter(or_(Voice.slot_lock_expires_at.is_(None), Voice.slot_lock_expires_at <= now))
            .order_by(Voice.last_used_at.asc())
            .limit(proactive_limit)
            .all()
        )

        for voice in stale_candidates:
            if _evict_voice(voice, "proactive_cleanup", {'max_idle_hours': max_idle_hours}):
                reclaimed += 1

    if reclaimed:
        db.session.commit()
        if queue_length > 0:
            process_voice_queue.delay()
        logger.info("Reclaimed %s idle voices (queue_length=%s)", reclaimed, queue_length)
    return reclaimed


@celery_app.task(
    bind=True,
    base=VoiceTask,
    name='voice.reset_stuck_allocations',
)
def reset_stuck_allocations(self, max_to_reset: Optional[int] = None, stale_after_seconds: Optional[int] = None):
    """Reset voices stuck in ALLOCATING beyond the configured timeout and re-enqueue."""
    from models.voice_model import (
        Voice,
        VoiceAllocationStatus,
        VoiceSlotEvent,
        VoiceSlotEventType,
        VoiceStatus,
    )

    now = datetime.utcnow()
    stale_seconds = stale_after_seconds
    if stale_seconds is None:
        stale_seconds = getattr(Config, "VOICE_ALLOCATION_STUCK_SECONDS", 600) or 600
    threshold = now - timedelta(seconds=stale_seconds)

    query = (
        Voice.query.filter(Voice.allocation_status == VoiceAllocationStatus.ALLOCATING)
        .filter(
            or_(
                Voice.slot_lock_expires_at.is_(None),
                Voice.slot_lock_expires_at <= now,
                Voice.updated_at <= threshold,
            )
        )
        .order_by(Voice.updated_at.asc())
    )
    if max_to_reset:
        query = query.limit(max_to_reset)

    stuck = query.all()
    if not stuck:
        return 0

    reset_count = 0
    for voice in stuck:
        try:
            voice.status = VoiceStatus.RECORDED
            voice.allocation_status = VoiceAllocationStatus.RECORDED
            voice.error_message = "stale_allocation_reset"
            voice.slot_lock_expires_at = None
            VoiceSlotQueue.enqueue(
                voice.id,
                {
                    "voice_id": voice.id,
                    "s3_key": voice.recording_s3_key or voice.s3_sample_key,
                    "filename": voice.sample_filename or f"voice_{voice.id}.mp3",
                    "user_id": voice.user_id,
                    "voice_name": voice.name,
                    "attempts": 0,
                    "service_provider": voice.service_provider,
                },
            )
            VoiceSlotEvent.log_event(
                voice_id=voice.id,
                user_id=voice.user_id,
                event_type=VoiceSlotEventType.ALLOCATION_QUEUED,
                reason="stuck_allocation_reset",
                metadata={"stale_seconds": stale_seconds},
            )
            reset_count += 1
        except Exception as exc:
            logger.error("Failed to reset stuck allocation for voice %s: %s", voice.id, exc)
            db.session.rollback()

    if reset_count:
        try:
            db.session.commit()
        except Exception as exc:
            logger.error("Failed to commit reset of stuck allocations: %s", exc)
            db.session.rollback()
            raise
        process_voice_queue.delay()
        logger.info("Reset %s stuck allocations", reset_count)
    return reset_count


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
    'voice-reset-stuck-allocations': {
        'task': 'voice.reset_stuck_allocations',
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
        from utils.voice_slot_manager import VoiceSlotManager

        voice = (
            Voice.query.filter_by(id=voice_id)
            .with_for_update()
            .first()
        )
        if not voice:
            logger.error("Voice record %s not found during allocation", voice_id)
            VoiceSlotManager._release_voice_lock(voice_id)
            return False

        provider = service_provider or voice.service_provider

        # Idempotency: if already allocated with remote ID and marked ready, short-circuit
        if voice.elevenlabs_voice_id and voice.allocation_status == VoiceAllocationStatus.READY:
            VoiceSlotEvent.log_event(
                voice_id=voice.id,
                user_id=user_id,
                event_type=VoiceSlotEventType.ALLOCATION_COMPLETED,
                reason="idempotent_skip",
                metadata={"external_voice_id": voice.elevenlabs_voice_id, "service_provider": provider},
            )
            VoiceSlotQueue.remove(voice.id)
            db.session.commit()
            VoiceSlotManager._release_voice_lock(voice_id)
            logger.info("Voice %s already allocated; skipping duplicate clone", voice_id)
            return True

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
            VoiceSlotManager._release_voice_lock(voice_id)
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
                VoiceSlotManager._release_voice_lock(voice_id)
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
            VoiceSlotManager._release_voice_lock(voice_id)
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
        VoiceSlotManager._release_voice_lock(voice_id)
        logger.error("Voice allocation failed for voice_id=%s: %s", voice_id, result)
        return False

    except Exception as e:
        logger.exception("Exception in allocate_voice_slot: %s", e)
        try:
            from utils.voice_slot_manager import VoiceSlotManager as _VSM
            _VSM._release_voice_lock(voice_id)
        except Exception:
            pass
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
