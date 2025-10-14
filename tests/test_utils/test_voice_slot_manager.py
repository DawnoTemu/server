from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from database import db
from utils.voice_slot_manager import (
    VoiceSlotManager,
    VoiceSlotManagerError,
)
from models.voice_model import (
    Voice,
    VoiceAllocationStatus,
    VoiceStatus,
    VoiceSlotEventType,
)
from models.user_model import User


class DummySession:
    def __init__(self):
        self.flush_calls = 0
        self.commit_calls = 0
        self.rollback_calls = 0

    def flush(self):
        self.flush_calls += 1

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1

    def refresh(self, _):
        return None


@pytest.fixture
def dummy_session(monkeypatch):
    session = DummySession()
    monkeypatch.setattr("utils.voice_slot_manager.db", SimpleNamespace(session=session))
    return session


def make_voice(**overrides):
    defaults = {
        "id": 7,
        "user_id": 42,
        "name": "Test Voice",
        "recording_s3_key": "voice_samples/42/voice_7.wav",
        "s3_sample_key": None,
        "sample_filename": "voice_7.wav",
        "status": VoiceStatus.RECORDED,
        "allocation_status": VoiceAllocationStatus.RECORDED,
        "service_provider": "elevenlabs",
        "elevenlabs_voice_id": None,
        "elevenlabs_allocated_at": None,
        "slot_lock_expires_at": None,
        "error_message": None,
        "user": SimpleNamespace(id=42),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_ready_voice_short_circuits(monkeypatch, dummy_session):
    now = datetime.utcnow()
    voice = make_voice(
        status=VoiceStatus.READY,
        allocation_status=VoiceAllocationStatus.READY,
        elevenlabs_voice_id="remote-voice",
        elevenlabs_allocated_at=now,
    )
    state = VoiceSlotManager.ensure_active_voice(voice)
    assert state.status == VoiceSlotManager.STATUS_READY
    assert state.metadata["voice_id"] == voice.id
    assert state.metadata["elevenlabs_voice_id"] == "remote-voice"
    assert dummy_session.flush_calls == 0


def test_allocating_voice_uses_queue_metadata(monkeypatch, dummy_session):
    voice = make_voice(
        status=VoiceStatus.PROCESSING,
        allocation_status=VoiceAllocationStatus.ALLOCATING,
    )
    monkeypatch.setattr("utils.voice_slot_manager.VoiceSlotQueue.position", lambda voice_id: 3)
    monkeypatch.setattr("utils.voice_slot_manager.VoiceSlotQueue.length", lambda: 7)

    state = VoiceSlotManager.ensure_active_voice(voice)

    assert state.status == VoiceSlotManager.STATUS_ALLOCATING
    assert state.metadata["queue_position"] == 3
    assert state.metadata["queue_length"] == 7


def test_queue_known_voice_returns_queued(monkeypatch, dummy_session):
    voice = make_voice()
    monkeypatch.setattr("utils.voice_slot_manager.VoiceSlotQueue.is_enqueued", lambda voice_id: True)
    monkeypatch.setattr("utils.voice_slot_manager.VoiceSlotQueue.position", lambda voice_id: 1)
    monkeypatch.setattr("utils.voice_slot_manager.VoiceSlotQueue.length", lambda: 4)

    state = VoiceSlotManager.ensure_active_voice(voice)
    assert state.status == VoiceSlotManager.STATUS_QUEUED
    assert state.metadata["queue_position"] == 1
    assert state.metadata["queue_length"] == 4


def test_enqueue_when_capacity_full(monkeypatch, dummy_session):
    voice = make_voice()
    monkeypatch.setattr("utils.voice_slot_manager.VoiceSlotQueue.is_enqueued", lambda *_: False)
    monkeypatch.setattr("utils.voice_slot_manager.VoiceSlotQueue.length", lambda: 2)
    monkeypatch.setattr("utils.voice_slot_manager.VoiceSlotQueue.position", lambda _: 0)
    enqueue_calls = []
    monkeypatch.setattr(
        "utils.voice_slot_manager.VoiceSlotQueue.enqueue",
        lambda voice_id, payload: enqueue_calls.append((voice_id, payload)),
    )
    monkeypatch.setattr(
        "tasks.voice_tasks.process_voice_queue.delay",
        lambda: enqueue_calls.append(("process", None)),
    )
    monkeypatch.setattr(
        "utils.voice_slot_manager.VoiceSlotEvent.log_event",
        lambda **kwargs: enqueue_calls.append(("event", kwargs)),
        raising=False,
    )
    monkeypatch.setattr(
        "models.voice_model.VoiceModel.available_slot_capacity",
        staticmethod(lambda provider=None: 0),
    )

    state = VoiceSlotManager.ensure_active_voice(voice)

    assert state.status == VoiceSlotManager.STATUS_QUEUED
    assert enqueue_calls, "enqueue should be invoked when capacity is zero"
    assert dummy_session.commit_calls == 1


def test_initiate_allocation_sets_processing(monkeypatch, dummy_session):
    voice = make_voice()

    monkeypatch.setattr("utils.voice_slot_manager.VoiceSlotQueue.is_enqueued", lambda *_: False)
    monkeypatch.setattr(
        "models.voice_model.VoiceModel.available_slot_capacity",
        staticmethod(lambda provider=None: 3),
    )
    monkeypatch.setattr("utils.voice_slot_manager.VoiceSlotQueue.length", lambda: 0)
    monkeypatch.setattr("utils.voice_slot_manager.VoiceSlotQueue.position", lambda _: None)
    events = []
    monkeypatch.setattr(
        "utils.voice_slot_manager.VoiceSlotEvent.log_event",
        lambda **kwargs: events.append(kwargs),
        raising=False,
    )
    task_stub = MagicMock()
    task_stub.delay.return_value = MagicMock(id="task-123")
    monkeypatch.setattr("tasks.voice_tasks.allocate_voice_slot", task_stub)

    state = VoiceSlotManager.ensure_active_voice(voice)

    assert state.status == VoiceSlotManager.STATUS_ALLOCATING
    assert voice.status == VoiceStatus.PROCESSING
    assert voice.allocation_status == VoiceAllocationStatus.ALLOCATING
    assert voice.slot_lock_expires_at is not None
    assert dummy_session.flush_calls == 1
    assert dummy_session.commit_calls == 1
    assert events and events[0]["event_type"] == VoiceSlotEventType.SLOT_LOCK_ACQUIRED
    task_stub.delay.assert_called_once()


def test_missing_recording_raises(monkeypatch, dummy_session):
    voice = make_voice(recording_s3_key=None, s3_sample_key=None)
    with pytest.raises(VoiceSlotManagerError):
        VoiceSlotManager.ensure_active_voice(voice)


def test_missing_sample_ready_voice_allowed(monkeypatch, dummy_session):
    voice = make_voice(
        recording_s3_key=None,
        s3_sample_key=None,
        status=VoiceStatus.READY,
        allocation_status=VoiceAllocationStatus.READY,
        elevenlabs_voice_id="remote",
    )
    state = VoiceSlotManager.ensure_active_voice(voice)
    assert state.status == VoiceSlotManager.STATUS_READY


def test_ensure_active_voice_refreshes_stale_state(app, mocker):
    mocker.patch("utils.voice_slot_manager.VoiceSlotQueue.position", return_value=None)
    mocker.patch("utils.voice_slot_manager.VoiceSlotQueue.length", return_value=0)

    with app.app_context():
        user = User(
            email="stale@example.com",
            is_active=True,
            email_confirmed=True,
        )
        user.set_password("Password123!")
        db.session.add(user)
        db.session.commit()

        voice = Voice(
            name="Stale Voice",
            user_id=user.id,
            recording_s3_key="voice_samples/stale.wav",
            status=VoiceStatus.RECORDED,
            allocation_status=VoiceAllocationStatus.RECORDED,
        )
        db.session.add(voice)
        db.session.commit()

        stale_voice = Voice.query.get(voice.id)
        db.session.expunge(stale_voice)

        Voice.query.filter_by(id=voice.id).update(
            {
                "allocation_status": VoiceAllocationStatus.ALLOCATING,
                "status": VoiceStatus.PROCESSING,
            },
            synchronize_session=False,
        )
        db.session.commit()

        mocker.patch.object(
            VoiceSlotManager,
            "_initiate_allocation",
            side_effect=AssertionError("Allocation should not be re-triggered for stale voice state"),
        )

        state = VoiceSlotManager.ensure_active_voice(stale_voice)
        assert state.status == VoiceSlotManager.STATUS_ALLOCATING
        assert state.metadata["allocation_status"] == VoiceAllocationStatus.ALLOCATING
