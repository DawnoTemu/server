import logging
from typing import Tuple

from database import db
from models.audio_model import AudioModel, AudioStatus, AudioStory
from models.story_model import StoryModel
from models.voice_model import VoiceModel
from models.credit_model import (
    debit as credit_debit,
    refund_by_audio,
    InsufficientCreditsError,
)
from utils.credits import calculate_required_credits
from utils.voice_slot_manager import VoiceSlotManager, VoiceSlotManagerError
from utils.redis_client import RedisClient


logger = logging.getLogger("audio_controller")

# Short TTL for request deduplication (seconds)
SYNTH_DEDUP_TTL = 10


class AudioController:
    """Controller for audio-related operations."""

    @staticmethod
    def check_audio_exists(voice_id: int, story_id: int) -> Tuple[bool, dict, int]:
        """Check if audio exists for a voice and story."""
        try:
            voice = VoiceModel.get_voice_by_id(voice_id)
            if not voice:
                return False, {"error": "Voice not found"}, 404

            exists = AudioModel.check_audio_exists(voice.id, story_id)
            return True, {"exists": exists}, 200
        except Exception as exc:
            logger.error("Error checking if audio exists: %s", exc)
            return False, {"error": str(exc)}, 500

    @staticmethod
    def get_audio(voice_id: int, story_id: int, range_header=None):
        """Retrieve audio data for a voice/story combination."""
        try:
            voice = VoiceModel.get_voice_by_id(voice_id)
            if not voice:
                return False, {"error": "Voice not found"}, 404, None

            success, data, extra = AudioModel.get_audio(voice.id, story_id, range_header)
            if not success:
                return False, {"error": str(data)}, 404, None

            status_code = 206 if range_header else 200
            return True, data, status_code, extra
        except Exception as exc:
            logger.error("Error retrieving audio: %s", exc)
            return False, {"error": f"Failed to retrieve audio: {exc}"}, 500, None

    @staticmethod
    def get_audio_presigned_url(voice_id: int, story_id: int, expires_in: int = 3600):
        """Produce a presigned S3 URL for direct audio download."""
        try:
            voice = VoiceModel.get_voice_by_id(voice_id)
            if not voice:
                return False, "Voice not found", 404

            success, result, status = AudioController.check_audio_exists(voice_id, story_id)
            if not success:
                return success, result, status
            if not result.get("exists", False):
                return False, "Audio not found", 404

            success, url = AudioModel.get_audio_presigned_url(voice.id, story_id, expires_in)
            if not success:
                return False, {"error": f"Failed to generate presigned URL: {url}"}, 500

            return True, url, 200
        except Exception as exc:
            logger.error("Error generating audio URL: %s", exc)
            return False, {"error": f"Failed to generate audio URL: {exc}"}, 500

    @staticmethod
    def synthesize_audio(voice_id: int, story_id: int):
        """Kick off audio synthesis for a story using the specified voice."""
        try:
            voice = VoiceModel.get_voice_by_id(voice_id)
            if not voice:
                return False, {"error": "Voice not found"}, 404

            story = StoryModel.get_story_by_id(story_id)
            if not story:
                return False, {"error": "Story not found"}, 404

            text = story.get("content")
            if not text:
                return False, {"error": "Story text not found in story"}, 400

            # Request deduplication: prevent duplicate tasks from rapid clicks
            dedup_key = f"audio:synth:dedup:{voice_id}:{story_id}"
            try:
                redis_client = RedisClient.get_client()
                # set() with nx=True returns True only if key was created (not existing)
                if not redis_client.set(dedup_key, "1", nx=True, ex=SYNTH_DEDUP_TTL):
                    # Key already exists - request is being processed
                    logger.info("Duplicate synthesis request blocked: voice=%s story=%s", voice_id, story_id)
                    audio_record = AudioModel.find_or_create_audio_record(story_id, voice.id, voice.user_id)
                    return True, {
                        "status": "pending",
                        "id": audio_record.id,
                        "message": "Audio synthesis request already in progress",
                    }, 202
            except Exception as dedup_exc:
                # Don't fail if Redis is unavailable; continue without dedup
                logger.warning("Request deduplication check failed: %s", dedup_exc)

            audio_record = AudioModel.find_or_create_audio_record(story_id, voice.id, voice.user_id)

            if audio_record.status == AudioStatus.READY.value and audio_record.s3_key:
                success, url = AudioModel.get_audio_presigned_url(voice.id, story_id)
                if success:
                    return True, {"status": "ready", "url": url, "id": audio_record.id}, 200
                return False, {"error": "Failed to generate URL"}, 500

            if audio_record.status == AudioStatus.PROCESSING.value:
                return True, {
                    "status": "processing",
                    "id": audio_record.id,
                    "message": "Audio synthesis is already in progress",
                }, 202

            if audio_record.status == AudioStatus.PENDING.value and audio_record.credits_charged:
                return True, {
                    "status": "pending",
                    "id": audio_record.id,
                    "message": "Audio synthesis request already queued",
                    "error_message": audio_record.error_message,
                }, 202

            retry_after_error = audio_record.status == AudioStatus.ERROR.value
            if retry_after_error:
                audio_record.status = AudioStatus.PENDING.value
                audio_record.error_message = None

            required = calculate_required_credits(text)

            audio_record.status = AudioStatus.PENDING.value
            audio_record.credits_charged = required

            debit_performed = False
            try:
                _, _debit_tx, _ = credit_debit(
                    user_id=voice.user_id,
                    amount=required,
                    reason=f"audio_synthesis:{story_id}",
                    audio_story_id=audio_record.id,
                    story_id=story_id,
                    auto_commit=False,
                )
                debit_performed = True
            except InsufficientCreditsError as exc:
                db.session.rollback()
                return False, {"error": str(exc), "required": required}, 402
            except Exception as exc:
                db.session.rollback()
                logger.error("Error debiting credits: %s", exc)
                return False, {"error": "Failed to charge credits"}, 500

            request_meta = {"story_id": story_id, "audio_story_id": audio_record.id}
            def _mark_audio_error(msg: str, status_code: int):
                """Rollback pending debit and mark audio as error."""
                try:
                    db.session.rollback()
                except Exception:
                    pass
                fresh = None
                if hasattr(db.session, "get"):
                    try:
                        fresh = db.session.get(AudioStory, audio_record.id)
                    except Exception:
                        fresh = None
                try:
                    target = fresh or audio_record
                    if hasattr(db.session, "add"):
                        db.session.add(target)
                    target.status = AudioStatus.ERROR.value
                    target.error_message = msg
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                return False, {"error": msg}, status_code

            def _attempt_refund(reason: str):
                if not debit_performed:
                    return
                try:
                    refund_by_audio(audio_record.id, reason=reason)
                except Exception as refund_exc:
                    logger.error("Refund after %s failed: %s", reason, refund_exc)

            try:
                slot_state = VoiceSlotManager.ensure_active_voice(voice, request_metadata=request_meta)
            except VoiceSlotManagerError as exc:
                logger.warning("Voice slot manager error after debit: %s", exc)
                _attempt_refund("voice_slot_manager_error")
                return _mark_audio_error(str(exc), 409)
            except Exception as exc:
                logger.error("Unexpected voice slot manager error: %s", exc)
                _attempt_refund("voice_slot_manager_error")
                return _mark_audio_error("Failed to allocate voice", 500)

            remote_voice_id = (
                slot_state.metadata.get("elevenlabs_voice_id") or voice.elevenlabs_voice_id
            )
            if slot_state.status != VoiceSlotManager.STATUS_READY:
                remote_voice_id = remote_voice_id or voice.elevenlabs_voice_id
            if slot_state.status == VoiceSlotManager.STATUS_READY and not remote_voice_id:
                logger.error("Voice %s ready without remote identifier", voice.id)
                _attempt_refund("missing_remote_voice_id")
                return _mark_audio_error("Voice is ready but missing remote identifier", 500)
            if remote_voice_id:
                slot_state.metadata.setdefault("elevenlabs_voice_id", remote_voice_id)

            if slot_state.status == VoiceSlotManager.STATUS_READY:
                audio_record.status = AudioStatus.PROCESSING.value
            else:
                audio_record.status = AudioStatus.PENDING.value

            try:
                from tasks.audio_tasks import synthesize_audio_task

                task = synthesize_audio_task.delay(audio_record.id, voice.id, story_id, text)
                logger.info(
                    "Queued audio synthesis task %s for audio ID %s", task.id, audio_record.id
                )
            except Exception as exc:
                logger.error("Queueing synthesis task failed: %s", exc)
                _attempt_refund("queue_failed")
                return _mark_audio_error("Failed to queue synthesis task", 503)

            try:
                db.session.commit()
            except Exception as exc:
                logger.error("Commit failed after queueing audio %s: %s", audio_record.id, exc)
                db.session.rollback()
                return False, {"error": "Failed to persist audio request"}, 500

            response_status = (
                "processing"
                if slot_state.status == VoiceSlotManager.STATUS_READY
                else slot_state.status
            )
            message = (
                "Audio synthesis has been queued"
                if slot_state.status == VoiceSlotManager.STATUS_READY
                else (
                    "Voice allocation is in progress"
                    if slot_state.status == VoiceSlotManager.STATUS_ALLOCATING
                    else "Voice has been queued for allocation"
                )
            )

            return True, {
                "status": response_status,
                "id": audio_record.id,
                "voice": slot_state.metadata,
                "message": message,
            }, 202

        except Exception as exc:
            logger.error("Error synthesizing audio: %s", exc)
            db.session.rollback()
            return False, {"error": str(exc)}, 500
