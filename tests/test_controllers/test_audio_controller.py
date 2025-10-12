from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from controllers.audio_controller import AudioController
from models.audio_model import AudioStatus
from utils.voice_slot_manager import VoiceSlotManager, VoiceSlotState, VoiceSlotManagerError


@pytest.fixture
def dummy_session(monkeypatch):
    class DummySession:
        def __init__(self):
            self.commit_calls = 0
            self.rollback_calls = 0

        def commit(self):
            self.commit_calls += 1

        def rollback(self):
            self.rollback_calls += 1

    session = DummySession()
    monkeypatch.setattr("controllers.audio_controller.db.session", session)
    return session


def make_voice(**overrides):
    defaults = {
        "id": 1,
        "user_id": 10,
        "elevenlabs_voice_id": "remote-voice",
        "service_provider": "elevenlabs",
        "allocation_status": "ready",
        "status": "ready",
        "error_message": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def make_audio_record(**overrides):
    defaults = {
        "id": 42,
        "status": AudioStatus.PENDING.value,
        "s3_key": None,
        "error_message": None,
        "credits_charged": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_check_audio_exists_success(monkeypatch):
    voice = make_voice()
    monkeypatch.setattr(
        "controllers.audio_controller.VoiceModel.get_voice_by_id",
        lambda voice_id: voice if voice_id == voice.id else None,
    )
    monkeypatch.setattr(
        "controllers.audio_controller.AudioModel.check_audio_exists",
        lambda voice_id, story_id: True,
    )

    success, data, status_code = AudioController.check_audio_exists(voice.id, 99)

    assert success is True
    assert data == {"exists": True}
    assert status_code == 200


def test_check_audio_exists_voice_missing(monkeypatch):
    monkeypatch.setattr(
        "controllers.audio_controller.VoiceModel.get_voice_by_id", lambda voice_id: None
    )

    success, data, status_code = AudioController.check_audio_exists(123, 99)

    assert success is False
    assert status_code == 404
    assert data["error"] == "Voice not found"


def test_synthesize_audio_returns_ready_url(monkeypatch, dummy_session):
    voice = make_voice()
    story = {"content": "Hello world"}
    audio_record = make_audio_record(status=AudioStatus.READY.value, s3_key="s3://audio.mp3")

    monkeypatch.setattr(
        "controllers.audio_controller.VoiceModel.get_voice_by_id", lambda voice_id: voice
    )
    monkeypatch.setattr(
        "controllers.audio_controller.StoryModel.get_story_by_id", lambda story_id: story
    )
    monkeypatch.setattr(
        "controllers.audio_controller.AudioModel.find_or_create_audio_record",
        lambda story_id, voice_id, user_id: audio_record,
    )
    monkeypatch.setattr(
        "controllers.audio_controller.AudioModel.get_audio_presigned_url",
        lambda voice_id, story_id, expires_in=3600: (True, "https://cdn/audio.mp3"),
    )

    success, data, status_code = AudioController.synthesize_audio(voice.id, 5)

    assert success is True
    assert data["status"] == "ready"
    assert data["url"] == "https://cdn/audio.mp3"
    assert status_code == 200


def test_synthesize_audio_processing_returns_202(monkeypatch, dummy_session):
    voice = make_voice()
    story = {"content": "Queued story"}
    audio_record = make_audio_record(status=AudioStatus.PROCESSING.value)

    monkeypatch.setattr(
        "controllers.audio_controller.VoiceModel.get_voice_by_id", lambda voice_id: voice
    )
    monkeypatch.setattr(
        "controllers.audio_controller.StoryModel.get_story_by_id", lambda story_id: story
    )
    monkeypatch.setattr(
        "controllers.audio_controller.AudioModel.find_or_create_audio_record",
        lambda story_id, voice_id, user_id: audio_record,
    )

    success, data, status_code = AudioController.synthesize_audio(voice.id, 8)

    assert success is True
    assert status_code == 202
    assert data["status"] == "processing"


def test_synthesize_audio_allocating_voice(monkeypatch, dummy_session):
    voice = make_voice(allocation_status="allocating", elevenlabs_voice_id=None)
    story = {"content": "Waiting story"}
    audio_record = make_audio_record()

    monkeypatch.setattr(
        "controllers.audio_controller.VoiceModel.get_voice_by_id", lambda voice_id: voice
    )
    monkeypatch.setattr(
        "controllers.audio_controller.StoryModel.get_story_by_id", lambda story_id: story
    )
    monkeypatch.setattr(
        "controllers.audio_controller.AudioModel.find_or_create_audio_record",
        lambda story_id, voice_id, user_id: audio_record,
    )
    monkeypatch.setattr(
        "controllers.audio_controller.VoiceSlotManager.ensure_active_voice",
        lambda voice, request_metadata=None: VoiceSlotState(
            VoiceSlotManager.STATUS_ALLOCATING, {"voice_id": voice.id}
        ),
    )
    monkeypatch.setattr(
        "controllers.audio_controller.calculate_required_credits", lambda text: 5
    )
    debit_calls = {}

    def fake_credit_debit(**kwargs):
        debit_calls["kwargs"] = kwargs
        return True, MagicMock(), 5

    monkeypatch.setattr("controllers.audio_controller.credit_debit", fake_credit_debit)
    task_mock = MagicMock()
    task_mock.id = "task-alloc"
    task_stub = MagicMock()
    task_stub.delay.return_value = task_mock
    monkeypatch.setattr("tasks.audio_tasks.synthesize_audio_task", task_stub)

    success, data, status_code = AudioController.synthesize_audio(voice.id, 7)

    assert success is True
    assert status_code == 202
    assert data["status"] == VoiceSlotManager.STATUS_ALLOCATING
    assert audio_record.status == AudioStatus.PENDING.value
    assert dummy_session.commit_calls >= 1
    assert debit_calls["kwargs"]["user_id"] == voice.user_id
    task_stub.delay.assert_called_once_with(
        audio_record.id, voice.id, 7, story["content"]
    )


def test_synthesize_audio_queues_task_when_ready(monkeypatch, dummy_session):
    voice = make_voice()
    story = {"content": "Narrate me"}
    audio_record = make_audio_record()

    monkeypatch.setattr(
        "controllers.audio_controller.VoiceModel.get_voice_by_id", lambda voice_id: voice
    )
    monkeypatch.setattr(
        "controllers.audio_controller.StoryModel.get_story_by_id", lambda story_id: story
    )
    monkeypatch.setattr(
        "controllers.audio_controller.AudioModel.find_or_create_audio_record",
        lambda story_id, voice_id, user_id: audio_record,
    )
    monkeypatch.setattr(
        "controllers.audio_controller.VoiceSlotManager.ensure_active_voice",
        lambda voice, request_metadata=None: VoiceSlotState(
            VoiceSlotManager.STATUS_READY, {"elevenlabs_voice_id": "remote-voice"}
        ),
    )
    monkeypatch.setattr(
        "controllers.audio_controller.calculate_required_credits", lambda text: 5
    )
    debit_calls = {}

    def fake_credit_debit(**kwargs):
        debit_calls["kwargs"] = kwargs
        return True, MagicMock(), 5

    monkeypatch.setattr("controllers.audio_controller.credit_debit", fake_credit_debit)
    task_mock = MagicMock()
    task_mock.id = "task-123"
    task_stub = MagicMock()
    task_stub.delay.return_value = task_mock
    monkeypatch.setattr("tasks.audio_tasks.synthesize_audio_task", task_stub)

    success, data, status_code = AudioController.synthesize_audio(voice.id, 11)

    assert success is True
    assert status_code == 202
    assert data["status"] == "processing"
    assert audio_record.status == AudioStatus.PROCESSING.value
    assert debit_calls["kwargs"]["user_id"] == voice.user_id
    task_stub.delay.assert_called_once_with(
        audio_record.id, voice.id, 11, story["content"]
    )


def test_synthesize_audio_voice_manager_error(monkeypatch, dummy_session):
    voice = make_voice()
    story = {"content": "Errored story"}
    audio_record = make_audio_record()

    monkeypatch.setattr(
        "controllers.audio_controller.VoiceModel.get_voice_by_id", lambda voice_id: voice
    )
    monkeypatch.setattr(
        "controllers.audio_controller.StoryModel.get_story_by_id", lambda story_id: story
    )
    monkeypatch.setattr(
        "controllers.audio_controller.AudioModel.find_or_create_audio_record",
        lambda story_id, voice_id, user_id: audio_record,
    )

    def raise_manager(*args, **kwargs):
        raise VoiceSlotManagerError("allocation failure")

    monkeypatch.setattr(
        "controllers.audio_controller.VoiceSlotManager.ensure_active_voice",
        raise_manager,
    )

    success, data, status_code = AudioController.synthesize_audio(voice.id, 3)

    assert success is False
    assert status_code == 409
    assert data["error"] == "allocation failure"
    assert audio_record.error_message == "allocation failure"
