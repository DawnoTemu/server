from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from models.audio_model import AudioStatus
from tasks.audio_tasks import synthesize_audio_task
from utils.voice_slot_manager import VoiceSlotManager, VoiceSlotState


@pytest.fixture(autouse=True)
def patch_config(monkeypatch):
    monkeypatch.setattr("config.Config.VOICE_QUEUE_POLL_INTERVAL", 10, raising=False)
    monkeypatch.setattr("config.Config.AUDIO_VOICE_ALLOCATION_MAX_ATTEMPTS", 3, raising=False)
    monkeypatch.setattr("config.Config.VOICE_WARM_HOLD_SECONDS", 900, raising=False)


@pytest.fixture
def stub_db_session(monkeypatch):
    class DummySession:
        def __init__(self):
            self.commit_calls = 0
            self.rollback_calls = 0

        def commit(self):
            self.commit_calls += 1

        def rollback(self):
            self.rollback_calls += 1

    session = DummySession()
    monkeypatch.setattr("tasks.audio_tasks.db.session", session)
    return session


def test_synthesize_audio_task_reschedules_when_voice_allocating(monkeypatch, stub_db_session):
    audio_story = SimpleNamespace(
        id=1,
        status=AudioStatus.PENDING.value,
        error_message=None,
    )
    voice = SimpleNamespace(
        id=2,
        user_id=1,
        elevenlabs_voice_id=None,
        last_used_at=None,
        slot_lock_expires_at=None,
    )

    class AudioStoryQuery:
        @staticmethod
        def get(_id):
            return audio_story

    class VoiceQuery:
        @staticmethod
        def get(_id):
            return voice

    monkeypatch.setattr(
        "models.audio_model.AudioStory", SimpleNamespace(query=AudioStoryQuery())
    )
    monkeypatch.setattr("models.voice_model.Voice", SimpleNamespace(query=VoiceQuery()))
    monkeypatch.setattr(
        "utils.voice_slot_manager.VoiceSlotManager.ensure_active_voice",
        lambda voice, request_metadata=None: VoiceSlotState(
            VoiceSlotManager.STATUS_ALLOCATING, {"voice_id": voice.id}
        ),
    )
    apply_async_mock = MagicMock()
    monkeypatch.setattr(
        "tasks.audio_tasks.synthesize_audio_task.apply_async", apply_async_mock
    )

    result = synthesize_audio_task.run(1, 2, 3, "hello world", attempt=0)

    assert isinstance(result, dict)
    assert result["rescheduled"] is True
    assert result["voice_status"] == VoiceSlotManager.STATUS_ALLOCATING
    apply_async_mock.assert_called_once()
    args, kwargs = apply_async_mock.call_args
    assert kwargs["kwargs"]["attempt"] == 1
    assert kwargs["countdown"] == 10
    assert audio_story.status == AudioStatus.PENDING.value
