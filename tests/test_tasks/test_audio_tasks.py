"""Tests for audio synthesis tasks.

Covers the critical paths in synthesize_audio_task:
  - Happy path: synthesis + storage success
  - Reschedule when voice is still allocating
  - Max attempts exceeded → error + refund
  - Voice not found → error + refund
  - Slot manager error → error + refund
  - Rate-limit (429) response → retry
  - Concurrency limit exceeded → retry
  - Synthesis failure → error + refund
  - Storage failure → error + refund
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

from models.audio_model import AudioStatus
from tasks.audio_tasks import synthesize_audio_task
from utils.voice_slot_manager import VoiceSlotManager, VoiceSlotManagerError, VoiceSlotState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_audio_story(**overrides):
    defaults = {
        "id": 1,
        "status": AudioStatus.PENDING.value,
        "error_message": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_voice(**overrides):
    defaults = {
        "id": 2,
        "user_id": 10,
        "elevenlabs_voice_id": "ext-voice-123",
        "service_provider": "elevenlabs",
        "last_used_at": None,
        "slot_lock_expires_at": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class DummySession:
    def __init__(self):
        self.commit_calls = 0
        self.rollback_calls = 0

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_config(monkeypatch):
    monkeypatch.setattr("config.Config.VOICE_QUEUE_POLL_INTERVAL", 10, raising=False)
    monkeypatch.setattr("config.Config.AUDIO_VOICE_ALLOCATION_MAX_ATTEMPTS", 3, raising=False)
    monkeypatch.setattr("config.Config.VOICE_WARM_HOLD_SECONDS", 900, raising=False)
    monkeypatch.setattr("config.Config.ELEVENLABS_SYNTHESIS_CONCURRENCY", 5, raising=False)
    monkeypatch.setattr("config.Config.ELEVENLABS_SYNTH_TTL", 180, raising=False)


@pytest.fixture
def stub_db(monkeypatch):
    session = DummySession()
    monkeypatch.setattr("tasks.audio_tasks.db", SimpleNamespace(session=session))
    return session


@pytest.fixture
def stub_events(monkeypatch):
    events = []

    def _log(**kwargs):
        events.append(kwargs)
        return SimpleNamespace(id=len(events))

    monkeypatch.setattr(
        "models.voice_model.VoiceSlotEvent.log_event",
        staticmethod(_log),
    )
    return events


@pytest.fixture
def stub_refund(monkeypatch):
    refunds = []
    monkeypatch.setattr(
        "models.credit_model.refund_by_audio",
        lambda audio_id, reason="": refunds.append({"audio_id": audio_id, "reason": reason}),
    )
    return refunds


@pytest.fixture(autouse=True)
def _app_ctx(app):
    with app.app_context():
        yield


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestSynthesizeAudioHappyPath:

    def test_synthesize_success_stores_audio_and_updates_voice(
        self, monkeypatch, stub_db, stub_events,
    ):
        audio_story = _make_audio_story()
        voice = _make_voice()

        monkeypatch.setattr(
            "models.audio_model.AudioStory",
            SimpleNamespace(query=SimpleNamespace(get=lambda _id: audio_story)),
        )
        monkeypatch.setattr(
            "models.voice_model.Voice",
            SimpleNamespace(query=SimpleNamespace(get=lambda _id: voice)),
        )
        monkeypatch.setattr(
            "utils.voice_slot_manager.VoiceSlotManager.ensure_active_voice",
            lambda v, request_metadata=None: VoiceSlotState(
                VoiceSlotManager.STATUS_READY,
                {"voice_id": v.id, "elevenlabs_voice_id": "ext-voice-123"},
            ),
        )
        monkeypatch.setattr(
            "models.audio_model.AudioModel.synthesize_speech",
            staticmethod(lambda vid, text: (True, b"audio-bytes")),
        )
        monkeypatch.setattr(
            "models.audio_model.AudioModel.store_audio",
            staticmethod(lambda data, vid, sid, rec: (True, "stored")),
        )

        result = synthesize_audio_task.run(1, 2, 3, "Pewnego razu...")

        assert result is True
        assert voice.last_used_at is not None
        assert stub_db.commit_calls >= 2


# ---------------------------------------------------------------------------
# Reschedule when voice not ready
# ---------------------------------------------------------------------------

class TestRescheduleWhenAllocating:

    def test_reschedules_when_voice_allocating(self, monkeypatch, stub_db):
        audio_story = _make_audio_story()
        voice = _make_voice(elevenlabs_voice_id=None)

        monkeypatch.setattr(
            "models.audio_model.AudioStory",
            SimpleNamespace(query=SimpleNamespace(get=lambda _id: audio_story)),
        )
        monkeypatch.setattr(
            "models.voice_model.Voice",
            SimpleNamespace(query=SimpleNamespace(get=lambda _id: voice)),
        )
        monkeypatch.setattr(
            "utils.voice_slot_manager.VoiceSlotManager.ensure_active_voice",
            lambda v, request_metadata=None: VoiceSlotState(
                VoiceSlotManager.STATUS_ALLOCATING, {"voice_id": v.id},
            ),
        )
        apply_async_mock = MagicMock()
        monkeypatch.setattr(
            "tasks.audio_tasks.synthesize_audio_task.apply_async", apply_async_mock,
        )

        result = synthesize_audio_task.run(1, 2, 3, "hello", attempt=0)

        assert isinstance(result, dict)
        assert result["rescheduled"] is True
        assert result["voice_status"] == VoiceSlotManager.STATUS_ALLOCATING
        apply_async_mock.assert_called_once()
        _, kwargs = apply_async_mock.call_args
        assert kwargs["kwargs"]["attempt"] == 1
        assert kwargs["countdown"] == 10
        assert audio_story.status == AudioStatus.PENDING.value

    def test_max_attempts_exceeded_errors_and_refunds(
        self, monkeypatch, stub_db, stub_refund,
    ):
        audio_story = _make_audio_story()
        voice = _make_voice(elevenlabs_voice_id=None)

        monkeypatch.setattr(
            "models.audio_model.AudioStory",
            SimpleNamespace(query=SimpleNamespace(get=lambda _id: audio_story)),
        )
        monkeypatch.setattr(
            "models.voice_model.Voice",
            SimpleNamespace(query=SimpleNamespace(get=lambda _id: voice)),
        )
        monkeypatch.setattr(
            "utils.voice_slot_manager.VoiceSlotManager.ensure_active_voice",
            lambda v, request_metadata=None: VoiceSlotState(
                VoiceSlotManager.STATUS_QUEUED, {"voice_id": v.id},
            ),
        )

        result = synthesize_audio_task.run(1, 2, 3, "hello", attempt=3)

        assert result is False
        assert audio_story.status == AudioStatus.ERROR.value
        assert "timed out" in (audio_story.error_message or "").lower()
        assert len(stub_refund) == 1
        assert stub_refund[0]["reason"] == "voice_allocation_timeout"


# ---------------------------------------------------------------------------
# Voice / audio story not found
# ---------------------------------------------------------------------------

class TestNotFound:

    def test_audio_story_not_found_returns_false(self, monkeypatch, stub_db):
        monkeypatch.setattr(
            "models.audio_model.AudioStory",
            SimpleNamespace(query=SimpleNamespace(get=lambda _id: None)),
        )
        monkeypatch.setattr(
            "models.voice_model.Voice",
            SimpleNamespace(query=SimpleNamespace(get=lambda _id: _make_voice())),
        )

        result = synthesize_audio_task.run(999, 2, 3, "text")
        assert result is False

    def test_voice_not_found_errors_and_refunds(
        self, monkeypatch, stub_db, stub_refund,
    ):
        audio_story = _make_audio_story()

        monkeypatch.setattr(
            "models.audio_model.AudioStory",
            SimpleNamespace(query=SimpleNamespace(get=lambda _id: audio_story)),
        )
        monkeypatch.setattr(
            "models.voice_model.Voice",
            SimpleNamespace(query=SimpleNamespace(get=lambda _id: None)),
        )

        result = synthesize_audio_task.run(1, 999, 3, "text")

        assert result is False
        assert audio_story.status == AudioStatus.ERROR.value
        assert len(stub_refund) == 1
        assert stub_refund[0]["reason"] == "voice_not_found"


# ---------------------------------------------------------------------------
# Slot manager error
# ---------------------------------------------------------------------------

class TestSlotManagerError:

    def test_slot_manager_error_marks_audio_error_and_refunds(
        self, monkeypatch, stub_db, stub_refund,
    ):
        audio_story = _make_audio_story()
        voice = _make_voice()

        monkeypatch.setattr(
            "models.audio_model.AudioStory",
            SimpleNamespace(query=SimpleNamespace(get=lambda _id: audio_story)),
        )
        monkeypatch.setattr(
            "models.voice_model.Voice",
            SimpleNamespace(query=SimpleNamespace(get=lambda _id: voice)),
        )
        monkeypatch.setattr(
            "utils.voice_slot_manager.VoiceSlotManager.ensure_active_voice",
            MagicMock(side_effect=VoiceSlotManagerError("sample missing")),
        )

        result = synthesize_audio_task.run(1, 2, 3, "text")

        assert result is False
        assert audio_story.status == AudioStatus.ERROR.value
        assert "sample missing" in (audio_story.error_message or "")
        assert len(stub_refund) == 1
        assert stub_refund[0]["reason"] == "voice_slot_manager_error"


# ---------------------------------------------------------------------------
# Synthesis failure → error + refund
# ---------------------------------------------------------------------------

class TestSynthesisFailure:

    def test_synthesis_api_failure_refunds_credits(
        self, monkeypatch, stub_db, stub_events, stub_refund,
    ):
        audio_story = _make_audio_story()
        voice = _make_voice()

        monkeypatch.setattr(
            "models.audio_model.AudioStory",
            SimpleNamespace(query=SimpleNamespace(get=lambda _id: audio_story)),
        )
        monkeypatch.setattr(
            "models.voice_model.Voice",
            SimpleNamespace(query=SimpleNamespace(get=lambda _id: voice)),
        )
        monkeypatch.setattr(
            "utils.voice_slot_manager.VoiceSlotManager.ensure_active_voice",
            lambda v, request_metadata=None: VoiceSlotState(
                VoiceSlotManager.STATUS_READY,
                {"voice_id": v.id, "elevenlabs_voice_id": "ext-voice-123"},
            ),
        )
        monkeypatch.setattr(
            "models.audio_model.AudioModel.synthesize_speech",
            staticmethod(lambda vid, text: (False, "Internal server error")),
        )

        result = synthesize_audio_task.run(1, 2, 3, "text")

        assert result is False
        assert audio_story.status == AudioStatus.ERROR.value
        assert len(stub_refund) == 1
        assert stub_refund[0]["reason"] == "synthesis_failed"

    def test_rate_limit_429_triggers_retry(
        self, monkeypatch, stub_db, stub_events,
    ):
        audio_story = _make_audio_story()
        voice = _make_voice()

        monkeypatch.setattr(
            "models.audio_model.AudioStory",
            SimpleNamespace(query=SimpleNamespace(get=lambda _id: audio_story)),
        )
        monkeypatch.setattr(
            "models.voice_model.Voice",
            SimpleNamespace(query=SimpleNamespace(get=lambda _id: voice)),
        )
        monkeypatch.setattr(
            "utils.voice_slot_manager.VoiceSlotManager.ensure_active_voice",
            lambda v, request_metadata=None: VoiceSlotState(
                VoiceSlotManager.STATUS_READY,
                {"voice_id": v.id, "elevenlabs_voice_id": "ext-voice-123"},
            ),
        )
        monkeypatch.setattr(
            "models.audio_model.AudioModel.synthesize_speech",
            staticmethod(lambda vid, text: (
                False,
                {"error": "rate_limited", "status_code": 429, "retry_after": 15},
            )),
        )

        retry_mock = MagicMock(side_effect=Exception("retry"))
        monkeypatch.setattr(
            "tasks.audio_tasks.synthesize_audio_task.retry", retry_mock,
        )

        with pytest.raises(Exception, match="retry"):
            synthesize_audio_task.run(1, 2, 3, "text")

        assert retry_mock.call_count >= 1
        first_call = retry_mock.call_args_list[0]
        assert first_call == call(countdown=15)
        assert audio_story.status == AudioStatus.PENDING.value

    def test_concurrent_request_string_triggers_retry(
        self, monkeypatch, stub_db, stub_events,
    ):
        audio_story = _make_audio_story()
        voice = _make_voice()

        monkeypatch.setattr(
            "models.audio_model.AudioStory",
            SimpleNamespace(query=SimpleNamespace(get=lambda _id: audio_story)),
        )
        monkeypatch.setattr(
            "models.voice_model.Voice",
            SimpleNamespace(query=SimpleNamespace(get=lambda _id: voice)),
        )
        monkeypatch.setattr(
            "utils.voice_slot_manager.VoiceSlotManager.ensure_active_voice",
            lambda v, request_metadata=None: VoiceSlotState(
                VoiceSlotManager.STATUS_READY,
                {"voice_id": v.id, "elevenlabs_voice_id": "ext-voice-123"},
            ),
        )
        monkeypatch.setattr(
            "models.audio_model.AudioModel.synthesize_speech",
            staticmethod(lambda vid, text: (
                False, "Too many concurrent requests"
            )),
        )

        retry_mock = MagicMock(side_effect=Exception("retry"))
        monkeypatch.setattr(
            "tasks.audio_tasks.synthesize_audio_task.retry", retry_mock,
        )

        with pytest.raises(Exception, match="retry"):
            synthesize_audio_task.run(1, 2, 3, "text")

        assert retry_mock.call_count >= 1
        assert audio_story.status == AudioStatus.PENDING.value


# ---------------------------------------------------------------------------
# Storage failure → error + refund
# ---------------------------------------------------------------------------

class TestStorageFailure:

    def test_storage_failure_refunds_credits(
        self, monkeypatch, stub_db, stub_events, stub_refund,
    ):
        audio_story = _make_audio_story()
        voice = _make_voice()

        monkeypatch.setattr(
            "models.audio_model.AudioStory",
            SimpleNamespace(query=SimpleNamespace(get=lambda _id: audio_story)),
        )
        monkeypatch.setattr(
            "models.voice_model.Voice",
            SimpleNamespace(query=SimpleNamespace(get=lambda _id: voice)),
        )
        monkeypatch.setattr(
            "utils.voice_slot_manager.VoiceSlotManager.ensure_active_voice",
            lambda v, request_metadata=None: VoiceSlotState(
                VoiceSlotManager.STATUS_READY,
                {"voice_id": v.id, "elevenlabs_voice_id": "ext-voice-123"},
            ),
        )
        monkeypatch.setattr(
            "models.audio_model.AudioModel.synthesize_speech",
            staticmethod(lambda vid, text: (True, b"audio-data")),
        )
        monkeypatch.setattr(
            "models.audio_model.AudioModel.store_audio",
            staticmethod(lambda data, vid, sid, rec: (False, "S3 upload failed")),
        )

        result = synthesize_audio_task.run(1, 2, 3, "text")

        assert result is False
        assert audio_story.status == AudioStatus.ERROR.value
        assert "S3 upload failed" in (audio_story.error_message or "")
        assert len(stub_refund) == 1
        assert stub_refund[0]["reason"] == "storage_failed"


# ---------------------------------------------------------------------------
# Missing remote voice ID
# ---------------------------------------------------------------------------

class TestMissingRemoteVoiceId:

    def test_ready_voice_without_remote_id_errors_and_refunds(
        self, monkeypatch, stub_db, stub_refund,
    ):
        audio_story = _make_audio_story()
        voice = _make_voice(elevenlabs_voice_id=None)

        monkeypatch.setattr(
            "models.audio_model.AudioStory",
            SimpleNamespace(query=SimpleNamespace(get=lambda _id: audio_story)),
        )
        monkeypatch.setattr(
            "models.voice_model.Voice",
            SimpleNamespace(query=SimpleNamespace(get=lambda _id: voice)),
        )
        monkeypatch.setattr(
            "utils.voice_slot_manager.VoiceSlotManager.ensure_active_voice",
            lambda v, request_metadata=None: VoiceSlotState(
                VoiceSlotManager.STATUS_READY,
                {"voice_id": v.id},
            ),
        )

        result = synthesize_audio_task.run(1, 2, 3, "text")

        assert result is False
        assert audio_story.status == AudioStatus.ERROR.value
        assert "remote identifier" in (audio_story.error_message or "").lower()
        assert len(stub_refund) == 1
        assert stub_refund[0]["reason"] == "missing_external_voice_id"
