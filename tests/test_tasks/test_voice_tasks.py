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
from tasks.voice_tasks import (
    allocate_voice_slot,
    process_voice_queue,
    reclaim_idle_voices,
    reset_stuck_allocations,
)


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


def test_allocate_voice_slot_honors_explicit_service_provider(monkeypatch, fake_db):
    class FakeVoiceQuery:
        def __init__(self, voice):
            self.voice = voice

        def get(self, _):
            return self.voice

    voice = SimpleNamespace(
        id=2,
        user_id=99,
        status=VoiceStatus.RECORDED,
        allocation_status=VoiceAllocationStatus.RECORDED,
        elevenlabs_voice_id=None,
        service_provider=VoiceServiceProvider.ELEVENLABS,
        error_message=None,
    )

    monkeypatch.setattr(voice_model_module, 'Voice', SimpleNamespace(query=FakeVoiceQuery(voice)))

    capacity_calls = []

    def fake_capacity(provider=None):
        capacity_calls.append(provider)
        return 0

    monkeypatch.setattr('models.voice_model.VoiceModel.available_slot_capacity', staticmethod(fake_capacity))

    enqueue_calls = []
    monkeypatch.setattr(
        'tasks.voice_tasks.VoiceSlotQueue.enqueue',
        lambda voice_id, payload, delay_seconds=0: enqueue_calls.append(payload.get('service_provider')),
    )
    monkeypatch.setattr('tasks.voice_tasks.process_voice_queue.apply_async', lambda *args, **kwargs: None)
    monkeypatch.setattr('tasks.voice_tasks.process_voice_queue.delay', lambda: None)
    monkeypatch.setattr('models.voice_model.VoiceSlotEvent.log_event', lambda **kwargs: None, raising=False)

    result = allocate_voice_slot.run(
        voice_id=2,
        s3_key="voice_samples/99/voice_2.wav",
        filename="sample.wav",
        user_id=99,
        voice_name="Voice",
        service_provider=VoiceServiceProvider.CARTESIA,
    )

    assert result == {"queued": True}
    assert capacity_calls and capacity_calls[0] == VoiceServiceProvider.CARTESIA
    assert enqueue_calls and enqueue_calls[0] == VoiceServiceProvider.CARTESIA


def test_allocate_voice_slot_passes_provider_to_clone(monkeypatch, fake_db):
    class FakeVoiceQuery:
        def __init__(self, voice):
            self.voice = voice

        def get(self, _):
            return self.voice

    voice = SimpleNamespace(
        id=3,
        user_id=77,
        status=VoiceStatus.RECORDED,
        allocation_status=VoiceAllocationStatus.RECORDED,
        elevenlabs_voice_id=None,
        service_provider=VoiceServiceProvider.ELEVENLABS,
        error_message=None,
        name="Explicit Provider Voice",
    )

    monkeypatch.setattr(voice_model_module, "Voice", SimpleNamespace(query=FakeVoiceQuery(voice)))
    monkeypatch.setattr(
        "models.voice_model.VoiceModel.available_slot_capacity",
        staticmethod(lambda provider=None: 5),
    )

    clone_calls = []

    def fake_clone(file_data, filename, user_id, voice_name, service_provider=None):
        clone_calls.append(service_provider)
        return True, {"voice_id": "remote-id"}

    monkeypatch.setattr("models.voice_model.VoiceModel._clone_voice_api", staticmethod(fake_clone))
    monkeypatch.setattr(
        "tasks.voice_tasks.S3Client.download_fileobj",
        staticmethod(lambda _: SimpleNamespace(read=lambda: b"audio-bytes")),
    )
    monkeypatch.setattr("tasks.voice_tasks.VoiceSlotQueue.remove", lambda *_: None)
    monkeypatch.setattr("models.voice_model.VoiceSlotEvent.log_event", lambda **kwargs: None, raising=False)

    result = allocate_voice_slot.run(
        voice_id=3,
        s3_key="voice_samples/77/voice_3.wav",
        filename="sample.wav",
        user_id=77,
        voice_name="Voice",
        service_provider=VoiceServiceProvider.CARTESIA,
    )

    assert result is True
    assert clone_calls and clone_calls[0] == VoiceServiceProvider.CARTESIA
    assert voice.service_provider == VoiceServiceProvider.CARTESIA


def test_allocate_voice_slot_idempotent_skip(monkeypatch, fake_db):
    class FakeVoiceQuery:
        def __init__(self, voice):
            self.voice = voice

        def get(self, _):
            return self.voice

    voice = SimpleNamespace(
        id=4,
        user_id=55,
        status=VoiceStatus.READY,
        allocation_status=VoiceAllocationStatus.READY,
        elevenlabs_voice_id="remote-existing",
        service_provider=VoiceServiceProvider.ELEVENLABS,
        error_message=None,
    )

    monkeypatch.setattr(voice_model_module, "Voice", SimpleNamespace(query=FakeVoiceQuery(voice)))
    monkeypatch.setattr(
        "models.voice_model.VoiceModel.available_slot_capacity",
        staticmethod(lambda provider=None: 1),
    )

    remove_calls = []
    monkeypatch.setattr("tasks.voice_tasks.VoiceSlotQueue.remove", lambda vid: remove_calls.append(vid))
    events = []
    monkeypatch.setattr("models.voice_model.VoiceSlotEvent.log_event", lambda **kwargs: events.append(kwargs), raising=False)
    # Ensure no S3 download occurs
    monkeypatch.setattr(
        "tasks.voice_tasks.S3Client.download_fileobj",
        staticmethod(lambda *_: (_ for _ in ()).throw(AssertionError("download should not be called"))),
    )

    result = allocate_voice_slot.run(
        voice_id=4,
        s3_key="voice_samples/55/voice_4.wav",
        filename="sample.wav",
        user_id=55,
        voice_name="Voice",
    )

    assert result is True
    assert remove_calls == [4]
    assert events and events[0]["reason"] == "idempotent_skip"
    assert voice.status == VoiceStatus.READY


def test_process_voice_queue_dispatches(monkeypatch):
    dispatched = []

    monkeypatch.setattr('models.voice_model.VoiceModel.available_slot_capacity', staticmethod(lambda provider=None: 2))
    queue = [{
        'voice_id': 1,
        's3_key': 'k',
        'filename': 'f',
        'user_id': 42,
        'voice_name': 'name',
        'attempts': 0,
        'service_provider': VoiceServiceProvider.ELEVENLABS,
    }]

    monkeypatch.setattr('tasks.voice_tasks.VoiceSlotQueue.dequeue_ready_batch', lambda limit=20: list(queue))
    monkeypatch.setattr('tasks.voice_tasks.allocate_voice_slot.delay', lambda **kwargs: dispatched.append(kwargs))
    monkeypatch.setattr('tasks.voice_tasks.VoiceSlotQueue.length', lambda: 1)

    processed = process_voice_queue.run()
    assert processed == 1
    assert dispatched and dispatched[0]['from_queue'] is True


def test_process_voice_queue_requeues_when_provider_full(monkeypatch):
    capacity_map = {
        VoiceServiceProvider.ELEVENLABS: 0,
        VoiceServiceProvider.CARTESIA: 2,
    }

    def capacity(provider=None):
        return capacity_map.get(provider, 2)

    monkeypatch.setattr('models.voice_model.VoiceModel.available_slot_capacity', staticmethod(capacity))

    queue = [
        {
            'voice_id': 1,
            's3_key': 'k1',
            'filename': 'f1',
            'user_id': 11,
            'voice_name': 'first',
            'attempts': 0,
            'service_provider': VoiceServiceProvider.ELEVENLABS,
        },
        {
            'voice_id': 2,
            's3_key': 'k2',
            'filename': 'f2',
            'user_id': 22,
            'voice_name': 'second',
            'attempts': 0,
            'service_provider': VoiceServiceProvider.CARTESIA,
        },
    ]

    requeued = []

    def fake_enqueue(voice_id, payload, delay_seconds=0):
        requeued.append((voice_id, payload, delay_seconds))

    dispatched = []

    monkeypatch.setattr('tasks.voice_tasks.VoiceSlotQueue.dequeue_ready_batch', lambda limit=20: list(queue))
    monkeypatch.setattr('tasks.voice_tasks.VoiceSlotQueue.enqueue', fake_enqueue)
    monkeypatch.setattr('tasks.voice_tasks.allocate_voice_slot.delay', lambda **kwargs: dispatched.append(kwargs))

    processed = process_voice_queue.run()
    assert processed == 1
    assert dispatched and dispatched[0]['voice_id'] == 2
    assert requeued and requeued[0][0] == 1
    assert requeued[0][2] >= 5


def test_process_voice_queue_fetches_provider_for_legacy_payload(monkeypatch):
    class FakeVoice:
        service_provider = VoiceServiceProvider.CARTESIA

    class FakeQuery:
        @staticmethod
        def get(_):
            return FakeVoice()

    monkeypatch.setattr('models.voice_model.Voice', SimpleNamespace(query=FakeQuery()))
    monkeypatch.setattr('models.voice_model.VoiceModel.available_slot_capacity', staticmethod(lambda provider=None: 1))

    queue = [{
        'voice_id': 99,
        's3_key': 'legacy',
        'filename': 'legacy.wav',
        'user_id': 44,
        'voice_name': 'legacy-voice',
        'attempts': 0,
    }]

    dispatched = []

    monkeypatch.setattr('tasks.voice_tasks.VoiceSlotQueue.dequeue_ready_batch', lambda limit=20: list(queue))
    monkeypatch.setattr('tasks.voice_tasks.allocate_voice_slot.delay', lambda **kwargs: dispatched.append(kwargs))

    processed = process_voice_queue.run()
    assert processed == 1
    assert dispatched and dispatched[0]['service_provider'] == VoiceServiceProvider.CARTESIA


def test_process_voice_queue_respects_capacity_per_provider(monkeypatch):
    capacity_map = {
        VoiceServiceProvider.ELEVENLABS: 1,
        VoiceServiceProvider.CARTESIA: 1,
    }

    def capacity(provider=None):
        return capacity_map.get(provider, 0)

    monkeypatch.setattr('models.voice_model.VoiceModel.available_slot_capacity', staticmethod(capacity))

    queue = [
        {
            'voice_id': 1,
            's3_key': 'k1',
            'filename': 'f1',
            'user_id': 11,
            'voice_name': 'first',
            'attempts': 0,
            'service_provider': VoiceServiceProvider.ELEVENLABS,
        },
        {
            'voice_id': 2,
            's3_key': 'k2',
            'filename': 'f2',
            'user_id': 22,
            'voice_name': 'second',
            'attempts': 0,
            'service_provider': VoiceServiceProvider.ELEVENLABS,
        },
        {
            'voice_id': 3,
            's3_key': 'k3',
            'filename': 'f3',
            'user_id': 33,
            'voice_name': 'third',
            'attempts': 0,
            'service_provider': VoiceServiceProvider.CARTESIA,
        },
    ]

    dispatched = []
    requeued = []
    monkeypatch.setattr('tasks.voice_tasks.VoiceSlotQueue.dequeue_ready_batch', lambda limit=20: list(queue))
    monkeypatch.setattr('tasks.voice_tasks.allocate_voice_slot.delay', lambda **kwargs: dispatched.append(kwargs))
    monkeypatch.setattr('tasks.voice_tasks.VoiceSlotQueue.enqueue', lambda voice_id, payload, delay_seconds=0: requeued.append((voice_id, delay_seconds)))

    processed = process_voice_queue.run()
    assert processed == 2  # one per provider
    assert {d['voice_id'] for d in dispatched} == {1, 3}
    assert requeued and requeued[0][0] == 2

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


def test_reset_stuck_allocations_requeues(monkeypatch, fake_db):
    now = datetime.utcnow()
    voice = SimpleNamespace(
        id=7,
        user_id=88,
        elevenlabs_voice_id=None,
        service_provider=VoiceServiceProvider.CARTESIA,
        allocation_status=VoiceAllocationStatus.ALLOCATING,
        status=VoiceStatus.PROCESSING,
        last_used_at=None,
        slot_lock_expires_at=now - timedelta(minutes=20),
        recording_s3_key="voice_samples/88/voice_7.wav",
        s3_sample_key=None,
        sample_filename="voice_7.wav",
        name="Stuck Voice",
        updated_at=now - timedelta(minutes=30),
    )

    class DummyAttr:
        def __eq__(self, _):
            return self

        def __le__(self, _):
            return self

        def is_(self, _):
            return self

        def asc(self):
            return self

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

    class StubVoice:
        allocation_status = DummyAttr()
        slot_lock_expires_at = DummyAttr()
        updated_at = DummyAttr()
        query = SimpleNamespace(filter=lambda *args, **kwargs: FakeQuery([voice]))

    monkeypatch.setattr(voice_model_module, "Voice", StubVoice)
    enqueue_calls = []
    monkeypatch.setattr(
        "tasks.voice_tasks.VoiceSlotQueue.enqueue",
        lambda voice_id, payload, delay_seconds=0: enqueue_calls.append((voice_id, payload)),
    )
    events = []
    monkeypatch.setattr("models.voice_model.VoiceSlotEvent.log_event", lambda **kwargs: events.append(kwargs), raising=False)
    process_calls = []
    monkeypatch.setattr("tasks.voice_tasks.process_voice_queue.delay", lambda: process_calls.append(True))

    reset = reset_stuck_allocations.run(stale_after_seconds=60)

    assert reset == 1
    assert enqueue_calls and enqueue_calls[0][0] == voice.id
    assert events and events[-1]["reason"] == "stuck_allocation_reset"
    assert process_calls
    assert voice.allocation_status == VoiceAllocationStatus.RECORDED
    assert voice.status == VoiceStatus.RECORDED
