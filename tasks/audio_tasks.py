"""
Audio synthesis tasks for StoryVoice.
This module contains Celery tasks for processing audio synthesis operations asynchronously.
"""

import logging
from datetime import datetime, timedelta

from celery import Task

from tasks import celery_app
from database import db

# Configure logger
logger = logging.getLogger("audio_tasks")


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
        logger.error("Task %s failed: %s", task_id, exc)
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
                        logger.info("Updated audio %s status to ERROR", audio_id)
                        # Refund credits for this audio attempt (idempotent)
                        try:
                            refund_by_audio(audio_id, reason="task_exception")
                            logger.info(
                                "Refunded credits for audio %s due to task failure", audio_id
                            )
                        except Exception as refund_exc:
                            logger.error(
                                "Failed to refund credits for audio %s: %s", audio_id, refund_exc
                            )
            except Exception as handler_exc:
                logger.error("Error in on_failure handler: %s", handler_exc)


@celery_app.task(
    bind=True,
    base=AudioTask,
    max_retries=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def synthesize_audio_task(self, audio_story_id, voice_id, story_id, text, attempt=0):
    """
    Asynchronous task to synthesize audio for a story.

    Args:
        audio_story_id: ID of the audio story record
        voice_id: ID of the voice in our database
        story_id: ID of the story
        text: Text to synthesize
        attempt: Number of times this task has been rescheduled while waiting for allocation

    Returns:
        bool | dict: Success status or diagnostic payload when rescheduled
    """
    logger.info(
        "Starting audio synthesis task for audio ID %s, voice %s, story %s (attempt %s)",
        audio_story_id,
        voice_id,
        story_id,
        attempt,
    )

    try:
        from config import Config
        from models.audio_model import AudioStory, AudioModel, AudioStatus
        from models.credit_model import refund_by_audio
        from models.voice_model import (
            Voice,
            VoiceServiceProvider,
            VoiceSlotEvent,
            VoiceSlotEventType,
        )
        from utils.concurrency_limiter import (
            ConcurrencyLimitExceeded,
            ConcurrencyLimiter,
        )
        from utils.voice_slot_manager import VoiceSlotManager, VoiceSlotManagerError

        audio_story = AudioStory.query.get(audio_story_id)
        if not audio_story:
            logger.error("Audio story record %s not found", audio_story_id)
            return False

        voice = Voice.query.get(voice_id)
        if not voice:
            logger.error("Voice %s not found", voice_id)
            audio_story.status = AudioStatus.ERROR.value
            audio_story.error_message = "Voice not found"
            db.session.commit()
            try:
                refund_by_audio(audio_story_id, reason="voice_not_found")
            except Exception as refund_exc:
                logger.error("Refund failed for audio %s: %s", audio_story_id, refund_exc)
            return False

        request_meta = {
            "audio_story_id": audio_story_id,
            "task_id": getattr(self.request, "id", None),
            "attempt": attempt,
        }

        try:
            slot_state = VoiceSlotManager.ensure_active_voice(voice, request_metadata=request_meta)
        except VoiceSlotManagerError as manager_exc:
            logger.error(
                "Voice slot manager error for voice %s (audio %s): %s",
                voice_id,
                audio_story_id,
                manager_exc,
            )
            audio_story.status = AudioStatus.ERROR.value
            audio_story.error_message = str(manager_exc)
            db.session.commit()
            try:
                refund_by_audio(audio_story_id, reason="voice_slot_manager_error")
            except Exception as refund_exc:
                logger.error("Refund failed for audio %s: %s", audio_story_id, refund_exc)
            return False

        max_wait_attempts = getattr(Config, "AUDIO_VOICE_ALLOCATION_MAX_ATTEMPTS", 5)
        if slot_state.status != VoiceSlotManager.STATUS_READY:
            if attempt >= max_wait_attempts:
                logger.error(
                    "Exceeded allocation wait attempts for audio %s (voice %s)",
                    audio_story_id,
                    voice_id,
                )
                audio_story.status = AudioStatus.ERROR.value
                audio_story.error_message = "Timed out waiting for voice allocation"
                db.session.commit()
                try:
                    refund_by_audio(audio_story_id, reason="voice_allocation_timeout")
                except Exception as refund_exc:
                    logger.error(
                        "Refund failed for audio %s after timeout: %s",
                        audio_story_id,
                        refund_exc,
                    )
                return False

            countdown = getattr(Config, "VOICE_QUEUE_POLL_INTERVAL", 30) or 30
            audio_story.status = AudioStatus.PENDING.value
            audio_story.error_message = None
            db.session.commit()

            synthesize_audio_task.apply_async(
                args=(audio_story_id, voice_id, story_id, text),
                kwargs={"attempt": attempt + 1},
                countdown=countdown,
            )
            logger.info(
                "Voice %s not ready (status=%s); rescheduled audio %s in %s seconds",
                voice_id,
                slot_state.status,
                audio_story_id,
                countdown,
            )
            return {"rescheduled": True, "voice_status": slot_state.status, "attempt": attempt + 1}

        remote_voice_id = (
            slot_state.metadata.get("elevenlabs_voice_id") or voice.elevenlabs_voice_id
        )
        if not remote_voice_id:
            logger.error("Voice %s ready without remote identifier", voice_id)
            audio_story.status = AudioStatus.ERROR.value
            audio_story.error_message = "Voice missing remote identifier"
            db.session.commit()
            try:
                refund_by_audio(audio_story_id, reason="missing_external_voice_id")
            except Exception as refund_exc:
                logger.error("Refund failed for audio %s: %s", audio_story_id, refund_exc)
            return False

        audio_story.status = AudioStatus.PROCESSING.value
        db.session.commit()

        limiter_wait = getattr(Config, "VOICE_QUEUE_POLL_INTERVAL", 60) or 60
        limiter_ttl = getattr(Config, "ELEVENLABS_SYNTH_TTL", 180) or 180
        # Use dedicated synthesis concurrency limit (not slot limit!)
        # ELEVENLABS_SLOT_LIMIT (30) = how many cloned voices can exist
        # ELEVENLABS_SYNTHESIS_CONCURRENCY (5) = how many parallel API calls allowed
        synth_limit = getattr(Config, "ELEVENLABS_SYNTHESIS_CONCURRENCY", 5) or 5

        # Acquire warm-hold lock BEFORE synthesis to prevent eviction during the operation
        warm_hold_seconds = getattr(Config, "VOICE_WARM_HOLD_SECONDS", 900) or 0
        if warm_hold_seconds > 0:
            now = datetime.utcnow()
            # Lock for duration of synthesis TTL + warm-hold window
            voice.slot_lock_expires_at = now + timedelta(seconds=limiter_ttl + warm_hold_seconds)
            db.session.commit()

        try:
            if voice.service_provider == VoiceServiceProvider.ELEVENLABS and synth_limit > 0:
                with ConcurrencyLimiter.guard(
                    "elevenlabs:synth", limit=synth_limit, ttl=limiter_ttl
                ):
                    synth_success, audio_data = AudioModel.synthesize_speech(
                        remote_voice_id, text
                    )
            else:
                synth_success, audio_data = AudioModel.synthesize_speech(remote_voice_id, text)
        except ConcurrencyLimitExceeded:
            wait_seconds = max(5, min(limiter_wait, 120))
            logger.info(
                "ElevenLabs synth concurrency limit reached; rescheduling audio %s in %s seconds",
                audio_story_id,
                wait_seconds,
            )
            audio_story.status = AudioStatus.PENDING.value
            audio_story.error_message = "Rate limited by ElevenLabs concurrency; retrying soon"
            db.session.commit()
            raise self.retry(countdown=wait_seconds)

        if not synth_success:
            if isinstance(audio_data, dict):
                is_rate_limit = (
                    audio_data.get("error") == "rate_limited"
                    or audio_data.get("status") == "too_many_concurrent_requests"
                    or audio_data.get("status_code") == 429
                )
                if is_rate_limit:
                    retry_after = audio_data.get("retry_after")
                    try:
                        retry_after = int(retry_after)
                    except Exception:
                        retry_after = None
                    wait_seconds = retry_after or max(5, min(limiter_wait, 120))
                    logger.info(
                        "ElevenLabs rate limit response; rescheduling audio %s in %s seconds",
                        audio_story_id,
                        wait_seconds,
                    )
                    audio_story.status = AudioStatus.PENDING.value
                    audio_story.error_message = "Rate limited by ElevenLabs; retrying soon"
                    db.session.commit()
                    raise self.retry(countdown=wait_seconds)

            if isinstance(audio_data, str) and "Too many concurrent requests" in audio_data:
                wait_seconds = max(5, min(limiter_wait, 120))
                logger.info(
                    "ElevenLabs concurrency message detected; rescheduling audio %s in %s seconds",
                    audio_story_id,
                    wait_seconds,
                )
                audio_story.status = AudioStatus.PENDING.value
                audio_story.error_message = "Rate limited by ElevenLabs; retrying soon"
                db.session.commit()
                raise self.retry(countdown=wait_seconds)

            logger.error("Speech synthesis failed: %s", audio_data)
            audio_story.status = AudioStatus.ERROR.value
            audio_story.error_message = str(audio_data)
            db.session.commit()
            try:
                refund_by_audio(audio_story_id, reason="synthesis_failed")
            except Exception as refund_exc:
                logger.error("Refund failed for audio %s: %s", audio_story_id, refund_exc)
            return False

        store_success, message = AudioModel.store_audio(audio_data, voice_id, story_id, audio_story)

        if not store_success:
            logger.error("Audio storage failed: %s", message)
            audio_story.status = AudioStatus.ERROR.value
            audio_story.error_message = message
            db.session.commit()
            try:
                refund_by_audio(audio_story_id, reason="storage_failed")
            except Exception as refund_exc:
                logger.error("Refund failed for audio %s: %s", audio_story_id, refund_exc)
            return False

        now = datetime.utcnow()
        voice.last_used_at = now
        warm_hold_seconds = getattr(Config, "VOICE_WARM_HOLD_SECONDS", 900) or 0
        if warm_hold_seconds > 0:
            voice.slot_lock_expires_at = now + timedelta(seconds=warm_hold_seconds)
        else:
            voice.slot_lock_expires_at = None

        VoiceSlotEvent.log_event(
            voice_id=voice.id,
            user_id=voice.user_id,
            event_type=VoiceSlotEventType.SLOT_LOCK_RELEASED,
            reason="audio_synthesis_completed",
            metadata={
                "audio_story_id": audio_story_id,
                "attempt": attempt,
                "voice_status": slot_state.status,
            },
        )
        db.session.commit()

        logger.info("Audio synthesis successful for audio ID %s", audio_story_id)
        return True

    except Exception as exc:
        logger.exception("Exception in synthesize_audio_task: %s", exc)
        raise
