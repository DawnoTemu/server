import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from config import Config
from database import db
from models.voice_model import (
    Voice,
    VoiceAllocationStatus,
    VoiceSlotEvent,
    VoiceSlotEventType,
    VoiceStatus,
    VoiceModel,
)
from utils.voice_slot_queue import VoiceSlotQueue
from utils.redis_client import RedisClient
from sqlalchemy.exc import InvalidRequestError


logger = logging.getLogger("voice_slot_manager")

# Default TTL for the per-voice allocation lock (seconds).
_VOICE_ALLOC_LOCK_TTL = 300


class VoiceSlotManagerError(Exception):
    """Raised when a voice cannot be allocated for synthesis."""


@dataclass
class VoiceSlotState:
    status: str
    metadata: Dict[str, Any]


class VoiceSlotManager:
    """Coordinate access to remote voice slots for synthesis."""

    STATUS_READY = "ready"
    STATUS_ALLOCATING = "allocating_voice"
    STATUS_QUEUED = "queued_for_slot"

    @classmethod
    def ensure_active_voice(
        cls,
        voice: Voice,
        *,
        request_metadata: Optional[Dict[str, Any]] = None,
    ) -> VoiceSlotState:
        """Ensure that the provided voice has an active remote slot.

        Returns the current slot state and auxiliary metadata describing any
        queue position, service provider, or remote identifiers.
        """
        if voice is None:
            raise VoiceSlotManagerError("Voice is required")

        voice = cls._reload_voice_state(voice)

        if not voice.recording_s3_key and not voice.s3_sample_key:
            if voice.elevenlabs_voice_id and voice.allocation_status == VoiceAllocationStatus.READY:
                logger.warning(
                    "Voice %s missing local sample but has remote ID; allowing ready state",
                    voice.id,
                )
            else:
                logger.error(
                    "Voice %s is missing a recording sample and cannot be allocated",
                    voice.id,
                )
                raise VoiceSlotManagerError(
                    "Voice sample is missing; please re-upload the recording."
                )

        metadata = {
            "voice_id": voice.id,
            "allocation_status": voice.allocation_status,
            "service_provider": voice.service_provider,
        }

        if voice.elevenlabs_voice_id and voice.allocation_status == VoiceAllocationStatus.READY:
            cls._extend_slot_lock(voice)
            metadata.update(
                {
                    "elevenlabs_voice_id": voice.elevenlabs_voice_id,
                    "allocated_at": voice.elevenlabs_allocated_at.isoformat()
                    if voice.elevenlabs_allocated_at
                    else None,
                }
            )
            return VoiceSlotState(cls.STATUS_READY, metadata)

        if voice.allocation_status == VoiceAllocationStatus.ALLOCATING:
            metadata.update(cls._queue_metadata(voice.id))
            return VoiceSlotState(cls.STATUS_ALLOCATING, metadata)

        if VoiceSlotQueue.is_enqueued(voice.id):
            metadata.update(cls._queue_metadata(voice.id))
            return VoiceSlotState(cls.STATUS_QUEUED, metadata)

        return cls._initiate_allocation(voice, metadata, request_metadata)

    @staticmethod
    def _queue_metadata(voice_id: int) -> Dict[str, Any]:
        position = VoiceSlotQueue.position(voice_id)
        queue_length = VoiceSlotQueue.length()
        result: Dict[str, Any] = {"queue_length": queue_length}
        if position is not None:
            result["queue_position"] = position
        return result

    @classmethod
    def _extend_slot_lock(cls, voice: Voice) -> None:
        """Extend slot_lock_expires_at to prevent eviction during active use."""
        warm_hold = getattr(Config, "VOICE_WARM_HOLD_SECONDS", 900) or 900
        voice.slot_lock_expires_at = datetime.utcnow() + timedelta(seconds=warm_hold)
        try:
            db.session.commit()
        except Exception:
            logger.warning("Failed to extend slot lock for voice %s", voice.id)
            db.session.rollback()

    # Redis key template for per-voice allocation locks.
    _ALLOC_LOCK_KEY = "voice_alloc_lock:{voice_id}"

    @classmethod
    def _acquire_voice_lock(cls, voice_id: int, ttl: int) -> bool:
        """Try to acquire a distributed lock for a voice allocation.

        Returns True when the lock is acquired, False when another worker
        already holds it (preventing duplicate clones).
        """
        try:
            client = RedisClient.get_client()
            key = cls._ALLOC_LOCK_KEY.format(voice_id=voice_id)
            return bool(client.set(key, "1", nx=True, ex=ttl))
        except Exception as exc:
            logger.warning("Redis lock unavailable for voice %s, allowing allocation: %s", voice_id, exc)
            return True  # Fail-open: proceed if Redis is down (rare)

    @classmethod
    def _release_voice_lock(cls, voice_id: int) -> None:
        try:
            client = RedisClient.get_client()
            key = cls._ALLOC_LOCK_KEY.format(voice_id=voice_id)
            client.delete(key)
        except Exception:
            pass  # Best-effort; TTL provides eventual cleanup

    @classmethod
    def _initiate_allocation(
        cls,
        voice: Voice,
        metadata: Dict[str, Any],
        request_metadata: Optional[Dict[str, Any]],
    ) -> VoiceSlotState:
        """Kick off allocation or enqueue when capacity is exhausted.

        Acquires a per-voice distributed lock to prevent concurrent duplicate
        allocations for the same voice.
        """
        lock_seconds = getattr(Config, "VOICE_SLOT_LOCK_SECONDS", 300) or 300

        # Prevent duplicate allocation: only one worker can hold this lock.
        if not cls._acquire_voice_lock(voice.id, lock_seconds):
            logger.info("Voice %s allocation already in progress (lock held); returning ALLOCATING", voice.id)
            metadata.update(cls._queue_metadata(voice.id))
            return VoiceSlotState(cls.STATUS_ALLOCATING, metadata)

        capacity = VoiceModel.available_slot_capacity(voice.service_provider)
        unlimited = capacity == float("inf")
        if not unlimited and capacity <= 0:
            cls._release_voice_lock(voice.id)
            cls._enqueue_voice(voice, request_metadata)
            metadata.update(cls._queue_metadata(voice.id))
            return VoiceSlotState(cls.STATUS_QUEUED, metadata)

        logger.info("Dispatching allocation for voice %s (capacity remaining: %s)", voice.id, capacity)
        metadata["queued"] = False

        voice.status = VoiceStatus.PROCESSING
        voice.allocation_status = VoiceAllocationStatus.ALLOCATING
        voice.error_message = None
        voice.slot_lock_expires_at = datetime.utcnow() + timedelta(seconds=lock_seconds)

        VoiceSlotEvent.log_event(
            voice_id=voice.id,
            user_id=voice.user_id,
            event_type=VoiceSlotEventType.SLOT_LOCK_ACQUIRED,
            reason="ensure_active_voice",
            metadata={"lock_seconds": lock_seconds, "request": request_metadata or {}},
        )

        try:
            db.session.flush()
        except Exception as exc:
            logger.exception("Failed to prepare allocation state for voice %s: %s", voice.id, exc)
            db.session.rollback()
            cls._release_voice_lock(voice.id)
            raise VoiceSlotManagerError("Failed to prepare allocation") from exc

        payload = {
            "voice_id": voice.id,
            "s3_key": voice.recording_s3_key or voice.s3_sample_key,
            "filename": voice.sample_filename or f"voice_{voice.id}.mp3",
            "user_id": voice.user_id,
            "voice_name": voice.name,
            "attempts": 0,
            "service_provider": voice.service_provider,
        }

        try:
            db.session.commit()
        except Exception as exc:
            logger.exception("Failed to persist allocation state for voice %s: %s", voice.id, exc)
            db.session.rollback()
            cls._release_voice_lock(voice.id)
            raise VoiceSlotManagerError("Failed to persist allocation state") from exc

        try:
            from tasks.voice_tasks import allocate_voice_slot  # local import to avoid circular dep

            allocate_voice_slot.delay(**payload)
        except Exception as exc:
            logger.exception("Queueing allocation task failed for voice %s: %s", voice.id, exc)
            cls._release_voice_lock(voice.id)
            raise VoiceSlotManagerError("Failed to queue allocation task") from exc

        metadata.update(cls._queue_metadata(voice.id))
        return VoiceSlotState(cls.STATUS_ALLOCATING, metadata)

    @staticmethod
    def _reload_voice_state(voice: Voice) -> Voice:
        """Refresh the provided voice instance to avoid stale allocation decisions."""
        if voice is None or voice.id is None:
            raise VoiceSlotManagerError("Voice is required")

        try:
            db.session.refresh(voice)
            return voice
        except InvalidRequestError:
            refreshed = Voice.query.filter_by(id=voice.id).first()
            if refreshed is None:
                raise VoiceSlotManagerError(f"Voice {voice.id} no longer exists")
            return refreshed

    @classmethod
    def _enqueue_voice(cls, voice: Voice, request_metadata: Optional[Dict[str, Any]]) -> None:
        payload = {
            "voice_id": voice.id,
            "s3_key": voice.recording_s3_key or voice.s3_sample_key,
            "filename": voice.sample_filename or f"voice_{voice.id}.mp3",
            "user_id": voice.user_id,
            "voice_name": voice.name,
            "attempts": 0,
            "service_provider": voice.service_provider,
        }

        VoiceSlotQueue.enqueue(voice.id, payload)
        VoiceSlotEvent.log_event(
            voice_id=voice.id,
            user_id=voice.user_id,
            event_type=VoiceSlotEventType.ALLOCATION_QUEUED,
            reason="ensure_active_voice_slot_limit",
            metadata={
                "request": request_metadata or {},
                "queue_size": VoiceSlotQueue.length(),
            },
        )

        try:
            db.session.commit()
        except Exception as exc:
            logger.exception("Failed to record queue event for voice %s: %s", voice.id, exc)
            db.session.rollback()
            raise VoiceSlotManagerError("Failed to enqueue allocation request") from exc

        try:
            from tasks.voice_tasks import process_voice_queue

            process_voice_queue.delay()
        except Exception:
            # Non-fatal: periodic beat will retry. We keep logging for visibility.
            logger.warning("Could not trigger queue processor immediately for voice %s", voice.id)
