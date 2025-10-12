from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import models.voice_model as voice_model_module
from models.voice_model import (
    Voice,
    VoiceAllocationStatus,
    VoiceSlotEventType,
    VoiceStatus,
    VoiceServiceProvider,
)
from tasks.voice_tasks import allocate_voice_slot, process_voice_queue, reclaim_idle_voices


class FakeSession:
    def __init__(self):
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


@pytest.fixture
def fake_db(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr('tasks.voice_tasks.db', SimpleNamespace(session=session))
    monkeypatch.setattr('models.voice_model.db', SimpleNamespace(session=session), raising=False)
    return session


def test_allocate_voice_slot_queues_when_limit_reached(monkeypatch, fake_db):
    class FakeVoiceQuery:
        def __init__(self, voice):
            self.voice = voice

        def get(self, _):
            return self.voice

    voice = SimpleNamespace(
        id=1,
        user_id=42,
        status=VoiceStatus.RECORDED,
        allocation_status=VoiceAllocationStatus.RECORDED,
        elevenlabs_voice_id=None,
        service_provider=VoiceServiceProvider.ELEVENLABS,
        error_message=None,
    )

    monkeypatch.setattr(voice_model_module, 'Voice', SimpleNamespace(query=FakeVoiceQuery(voice)))
    monkeypatch.setattr('models.voice_model.VoiceModel.available_slot_capacity', staticmethod(lambda provider=None: 0))

    enqueue_calls = []
    monkeypatch.setattr('tasks.voice_tasks.VoiceSlotQueue.enqueue', lambda voice_id, payload, delay_seconds=0: enqueue_calls.append((voice_id, payload, delay_seconds)))
    monkeypatch.setattr('tasks.voice_tasks.process_voice_queue.apply_async', lambda *args, **kwargs: enqueue_calls.append(('schedule', kwargs.get('countdown'))))
    monkeypatch.setattr('tasks.voice_tasks.process_voice_queue.delay', lambda: enqueue_calls.append(('delay', None)))

    events = []
    monkeypatch.setattr('models.voice_model.VoiceSlotEvent.log_event', lambda **kwargs: events.append(kwargs), raising=False)

    result = allocate_voice_slot.run(
        voice_id=1,
        s3_key="voice_samples/42/voice_1.wav",
        filename="sample.wav",
        user_id=42,
        voice_name="Voice",
    )

    assert result == {"queued": True}
    assert enqueue_calls, "Expected voice to be enqueued when capacity is zero"
    assert events[0]['event_type'] == VoiceSlotEventType.ALLOCATION_QUEUED
    assert voice.status == VoiceStatus.RECORDED
    assert voice.allocation_status == VoiceAllocationStatus.RECORDED


def test_process_voice_queue_dispatches(monkeypatch):
    dispatched = []

    monkeypatch.setattr('models.voice_model.VoiceModel.available_slot_capacity', staticmethod(lambda provider=None: 2))
    queue = [{'voice_id': 1, 's3_key': 'k', 'filename': 'f', 'user_id': 42, 'voice_name': 'name', 'attempts': 0}]

    def fake_dequeue():
        return queue.pop(0) if queue else None

    monkeypatch.setattr('tasks.voice_tasks.VoiceSlotQueue.dequeue', fake_dequeue)
    monkeypatch.setattr('tasks.voice_tasks.allocate_voice_slot.delay', lambda **kwargs: dispatched.append(kwargs))
    monkeypatch.setattr('tasks.voice_tasks.VoiceSlotQueue.length', lambda: 1)

    processed = process_voice_queue.run()
    assert processed == 1
    assert dispatched and dispatched[0]['from_queue'] is True


def test_reclaim_idle_voices_evicts_and_triggers_queue(monkeypatch, fake_db):
    now = datetime.utcnow()
    voice = SimpleNamespace(
        id=1,
        user_id=42,
        elevenlabs_voice_id='remote-id',
        service_provider=VoiceServiceProvider.ELEVENLABS,
        allocation_status=VoiceAllocationStatus.READY,
        status=VoiceStatus.READY,
        last_used_at=now - timedelta(minutes=30),
        slot_lock_expires_at=None,
    )

    class FakeQuery:
        def __init__(self, items):
            self.items = items

        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def limit(self, _):
            return self

        def all(self):
            return self.items

    class DummyAttr:
        def is_(self, _):
            return None

        def __le__(self, _):
            return None

        def __eq__(self, _):
            return None

        def asc(self):
            return self

    class StubVoice:
        allocation_status = DummyAttr()
        last_used_at = DummyAttr()
        slot_lock_expires_at = DummyAttr()
        query = SimpleNamespace(filter=lambda *args, **kwargs: FakeQuery([voice]))

    monkeypatch.setattr('tasks.voice_tasks.VoiceSlotQueue.length', lambda: 1)
    monkeypatch.setattr(voice_model_module, 'Voice', StubVoice)

    delete_calls = []
    monkeypatch.setattr('utils.voice_service.VoiceService.delete_voice', lambda **kwargs: (delete_calls.append(kwargs) or True, "ok"))

    events = []
    monkeypatch.setattr('models.voice_model.VoiceSlotEvent.log_event', lambda **kwargs: events.append(kwargs), raising=False)

    process_calls = []
    monkeypatch.setattr('tasks.voice_tasks.process_voice_queue.delay', lambda: process_calls.append(True))

    reclaimed = reclaim_idle_voices.run()

    assert reclaimed == 1
    assert delete_calls
    assert voice.elevenlabs_voice_id is None
    assert voice.status == VoiceStatus.RECORDED
    assert events[-1]['event_type'] == VoiceSlotEventType.SLOT_EVICTED
    assert process_calls


def test_reclaim_idle_voices_skips_when_remote_delete_fails(monkeypatch, fake_db):
    now = datetime.utcnow()
    voice = SimpleNamespace(
        id=3,
        user_id=77,
        elevenlabs_voice_id='remote-stuck',
        service_provider=VoiceServiceProvider.ELEVENLABS,
        allocation_status=VoiceAllocationStatus.READY,
        status=VoiceStatus.READY,
        last_used_at=now - timedelta(minutes=45),
        slot_lock_expires_at=None,
    )

    class FakeQuery:
        def __init__(self, items):
            self.items = items

        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def limit(self, _):
            return self

        def all(self):
            return self.items

    class DummyAttr:
        def is_(self, _):
            return None

        def __le__(self, _):
            return None

        def __eq__(self, _):
            return None

        def asc(self):
            return self

    class StubVoice:
        allocation_status = DummyAttr()
        last_used_at = DummyAttr()
        slot_lock_expires_at = DummyAttr()
        query = SimpleNamespace(filter=lambda *args, **kwargs: FakeQuery([voice]))

    monkeypatch.setattr('tasks.voice_tasks.VoiceSlotQueue.length', lambda: 1)
    monkeypatch.setattr(voice_model_module, 'Voice', StubVoice)
    monkeypatch.setattr(
        'utils.voice_service.VoiceService.delete_voice',
        lambda **kwargs: (False, "remote error"),
    )

    events = []
    monkeypatch.setattr('models.voice_model.VoiceSlotEvent.log_event', lambda **kwargs: events.append(kwargs), raising=False)
    monkeypatch.setattr('tasks.voice_tasks.process_voice_queue.delay', lambda: None)

    reclaimed = reclaim_idle_voices.run()

    assert reclaimed == 0
    assert voice.status == VoiceStatus.READY
    assert voice.elevenlabs_voice_id == 'remote-stuck'
    assert events == []
