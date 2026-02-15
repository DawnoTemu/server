"""Tests for core voice queuing tasks.

Covers the five critical tasks:
  - process_voice_recording
  - allocate_voice_slot
  - process_voice_queue
  - reclaim_idle_voices
  - reset_stuck_allocations
"""

from datetime import datetime, timedelta
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call

import pytest

from models.voice_model import (
    VoiceAllocationStatus,
    VoiceSlotEventType,
    VoiceStatus,
)
from tasks.voice_tasks import (
    allocate_voice_slot,
    process_voice_queue,
    process_voice_recording,
    reclaim_idle_voices,
    reset_stuck_allocations,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_voice(**overrides):
    defaults = {
        "id": 1,
        "user_id": 10,
        "name": "TestVoice",
        "recording_s3_key": "voice_samples/10/voice_1.wav",
        "s3_sample_key": None,
        "sample_filename": "voice_1.wav",
        "status": VoiceStatus.RECORDED,
        "allocation_status": VoiceAllocationStatus.RECORDED,
        "service_provider": "elevenlabs",
        "elevenlabs_voice_id": None,
        "elevenlabs_allocated_at": None,
        "last_used_at": None,
        "slot_lock_expires_at": None,
        "error_message": None,
        "recording_filesize": None,
        "updated_at": datetime.utcnow(),
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

    def flush(self):
        pass

    def refresh(self, obj):
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_config(monkeypatch):
    monkeypatch.setattr("config.Config.VOICE_QUEUE_POLL_INTERVAL", 30, raising=False)
    monkeypatch.setattr("config.Config.VOICE_QUEUE_BATCH_SIZE", 20, raising=False)
    monkeypatch.setattr("config.Config.VOICE_WARM_HOLD_SECONDS", 900, raising=False)
    monkeypatch.setattr("config.Config.VOICE_MAX_IDLE_HOURS", 24, raising=False)
    monkeypatch.setattr("config.Config.VOICE_ALLOCATION_STUCK_SECONDS", 600, raising=False)
    monkeypatch.setattr("config.Config.ELEVENLABS_SLOT_LIMIT", 30, raising=False)
    monkeypatch.setattr("config.Config.VOICE_SLOT_LOCK_SECONDS", 300, raising=False)


@pytest.fixture
def stub_db(monkeypatch):
    session = DummySession()
    monkeypatch.setattr("tasks.voice_tasks.db", SimpleNamespace(session=session))
    return session


@pytest.fixture
def stub_events(monkeypatch):
    """Capture VoiceSlotEvent.log_event calls without touching DB."""
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
def stub_queue(monkeypatch):
    """Provide controllable VoiceSlotQueue stubs."""
    state = {
        "items": [],
        "enqueued": [],
        "removed": [],
    }

    monkeypatch.setattr(
        "tasks.voice_tasks.VoiceSlotQueue.dequeue_ready_batch",
        lambda limit: state["items"][:limit],
    )
    monkeypatch.setattr(
        "tasks.voice_tasks.VoiceSlotQueue.enqueue",
        lambda vid, payload, delay_seconds=0: state["enqueued"].append(
            {"voice_id": vid, "payload": payload, "delay": delay_seconds}
        ),
    )
    monkeypatch.setattr(
        "tasks.voice_tasks.VoiceSlotQueue.remove",
        lambda vid: state["removed"].append(vid),
    )
    monkeypatch.setattr(
        "tasks.voice_tasks.VoiceSlotQueue.length",
        lambda: len(state["items"]),
    )
    return state


@pytest.fixture
def stub_metrics(monkeypatch):
    metrics = []
    monkeypatch.setattr(
        "tasks.voice_tasks.emit_metric",
        lambda name, value=1.0, **tags: metrics.append((name, value, tags)),
    )
    return metrics


@pytest.fixture(autouse=True)
def _app_ctx(app):
    """Provide Flask app context so Voice.query descriptor works during monkeypatch.

    monkeypatch.setattr reads the old value via getattr, which invokes
    Flask-SQLAlchemy's _QueryProperty.__get__ – that requires an active app
    context.  After each test, restore the original descriptor (monkeypatch
    only saves the *result* of __get__, not the descriptor itself).
    """
    from models.voice_model import Voice

    _orig = Voice.__dict__.get("query")
    with app.app_context():
        yield
    if _orig is not None:
        Voice.query = _orig


# ===================================================================
# process_voice_recording
# ===================================================================

class TestProcessVoiceRecording:

    def test_happy_path_records_metadata_no_allocation(
        self, monkeypatch, stub_db, stub_events, stub_metrics,
    ):
        """After processing, voice stays in RECORDED state and no allocation is dispatched."""
        voice = _make_voice()

        monkeypatch.setattr(
            "models.voice_model.Voice.query",
            SimpleNamespace(get=lambda _id: voice),
        )

        head_response = {
            "ContentLength": 12345,
            "ServerSideEncryption": "AES256",
            "StorageClass": "STANDARD",
            "ContentType": "audio/wav",
        }
        mock_s3_client = MagicMock()
        mock_s3_client.head_object.return_value = head_response

        monkeypatch.setattr(
            "utils.s3_client.S3Client.get_client", lambda: mock_s3_client,
        )
        monkeypatch.setattr(
            "utils.s3_client.S3Client.get_bucket_name", lambda: "test-bucket",
        )

        result = process_voice_recording.run(
            voice_id=1,
            s3_key="voice_samples/10/voice_1.wav",
            filename="voice_1.wav",
            user_id=10,
            voice_name="TestVoice",
        )

        assert result is True
        assert voice.status == VoiceStatus.RECORDED
        assert voice.recording_filesize == 12345
        assert stub_db.commit_calls == 1

        event_types = [e["event_type"] for e in stub_events]
        assert VoiceSlotEventType.RECORDING_PROCESSED in event_types

        # No allocation should have been dispatched (lazy allocation)
        metric_names = [m[0] for m in stub_metrics]
        assert "voice.process.completed" in metric_names
        assert "voice.process.dispatch_allocation" not in metric_names

    def test_voice_not_found_returns_false(self, monkeypatch, stub_db):
        monkeypatch.setattr(
            "models.voice_model.Voice.query",
            SimpleNamespace(get=lambda _id: None),
        )

        result = process_voice_recording.run(
            voice_id=999, s3_key="k", filename="f.wav", user_id=1,
        )
        assert result is False

    def test_s3_head_failure_is_non_fatal(
        self, monkeypatch, stub_db, stub_events, stub_metrics,
    ):
        voice = _make_voice()
        monkeypatch.setattr(
            "models.voice_model.Voice.query",
            SimpleNamespace(get=lambda _id: voice),
        )

        mock_s3_client = MagicMock()
        mock_s3_client.head_object.side_effect = RuntimeError("S3 down")
        monkeypatch.setattr("utils.s3_client.S3Client.get_client", lambda: mock_s3_client)
        monkeypatch.setattr("utils.s3_client.S3Client.get_bucket_name", lambda: "bucket")

        result = process_voice_recording.run(
            voice_id=1, s3_key="k", filename="f.wav", user_id=10,
        )
        assert result is True
        assert voice.status == VoiceStatus.RECORDED


# ===================================================================
# allocate_voice_slot
# ===================================================================

class TestAllocateVoiceSlot:

    def test_happy_path_clones_and_marks_ready(
        self, monkeypatch, stub_db, stub_events, stub_queue,
    ):
        voice = _make_voice()
        monkeypatch.setattr(
            "models.voice_model.Voice.query",
            SimpleNamespace(get=lambda _id: voice),
        )
        monkeypatch.setattr(
            "models.voice_model.VoiceModel.available_slot_capacity",
            staticmethod(lambda provider=None: 5),
        )
        monkeypatch.setattr(
            "utils.s3_client.S3Client.download_fileobj",
            lambda key: BytesIO(b"audio-bytes"),
        )
        monkeypatch.setattr(
            "models.voice_model.VoiceModel._clone_voice_api",
            staticmethod(lambda *a, **kw: (True, {"voice_id": "ext-voice-123"})),
        )
        monkeypatch.setattr(
            "tasks.voice_tasks.process_voice_queue.delay", lambda: None,
        )
        monkeypatch.setattr(
            "utils.voice_slot_manager.VoiceSlotManager._release_voice_lock",
            classmethod(lambda cls, vid: None),
        )

        result = allocate_voice_slot.run(
            voice_id=1, s3_key="k", filename="f.wav",
            user_id=10, voice_name="V",
        )

        assert result is True
        assert voice.elevenlabs_voice_id == "ext-voice-123"
        assert voice.status == VoiceStatus.READY
        assert voice.allocation_status == VoiceAllocationStatus.READY
        assert 1 in stub_queue["removed"]

    def test_idempotent_skip_when_already_ready(
        self, monkeypatch, stub_db, stub_queue,
    ):
        voice = _make_voice(
            elevenlabs_voice_id="existing-id",
            allocation_status=VoiceAllocationStatus.READY,
            status=VoiceStatus.READY,
        )
        monkeypatch.setattr(
            "models.voice_model.Voice.query",
            SimpleNamespace(get=lambda _id: voice),
        )
        monkeypatch.setattr(
            "utils.voice_slot_manager.VoiceSlotManager._release_voice_lock",
            classmethod(lambda cls, vid: None),
        )

        result = allocate_voice_slot.run(
            voice_id=1, s3_key="k", filename="f.wav", user_id=10,
        )
        assert result is True
        assert 1 in stub_queue["removed"]

    def test_enqueues_when_no_capacity(
        self, monkeypatch, stub_db, stub_events, stub_queue,
    ):
        voice = _make_voice()
        monkeypatch.setattr(
            "models.voice_model.Voice.query",
            SimpleNamespace(get=lambda _id: voice),
        )
        monkeypatch.setattr(
            "models.voice_model.VoiceModel.available_slot_capacity",
            staticmethod(lambda provider=None: 0),
        )
        monkeypatch.setattr(
            "utils.voice_slot_manager.VoiceSlotManager._release_voice_lock",
            classmethod(lambda cls, vid: None),
        )

        result = allocate_voice_slot.run(
            voice_id=1, s3_key="k", filename="f.wav", user_id=10,
        )
        assert result == {"queued": True}
        assert voice.allocation_status == VoiceAllocationStatus.RECORDED
        assert len(stub_queue["enqueued"]) == 1

    def test_s3_download_failure_marks_error(
        self, monkeypatch, stub_db, stub_events,
    ):
        voice = _make_voice()
        monkeypatch.setattr(
            "models.voice_model.Voice.query",
            SimpleNamespace(get=lambda _id: voice),
        )
        monkeypatch.setattr(
            "models.voice_model.VoiceModel.available_slot_capacity",
            staticmethod(lambda provider=None: 5),
        )
        monkeypatch.setattr(
            "utils.s3_client.S3Client.download_fileobj",
            MagicMock(side_effect=RuntimeError("S3 error")),
        )
        monkeypatch.setattr(
            "utils.voice_slot_manager.VoiceSlotManager._release_voice_lock",
            classmethod(lambda cls, vid: None),
        )

        result = allocate_voice_slot.run(
            voice_id=1, s3_key="k", filename="f.wav", user_id=10,
        )
        assert result is False
        assert voice.status == VoiceStatus.ERROR
        assert "download" in (voice.error_message or "").lower()

    def test_clone_api_failure_marks_error(
        self, monkeypatch, stub_db, stub_events,
    ):
        voice = _make_voice()
        monkeypatch.setattr(
            "models.voice_model.Voice.query",
            SimpleNamespace(get=lambda _id: voice),
        )
        monkeypatch.setattr(
            "models.voice_model.VoiceModel.available_slot_capacity",
            staticmethod(lambda provider=None: 5),
        )
        monkeypatch.setattr(
            "utils.s3_client.S3Client.download_fileobj",
            lambda key: BytesIO(b"audio"),
        )
        monkeypatch.setattr(
            "models.voice_model.VoiceModel._clone_voice_api",
            staticmethod(lambda *a, **kw: (False, "API rate limit")),
        )
        monkeypatch.setattr(
            "utils.voice_slot_manager.VoiceSlotManager._release_voice_lock",
            classmethod(lambda cls, vid: None),
        )

        result = allocate_voice_slot.run(
            voice_id=1, s3_key="k", filename="f.wav", user_id=10,
        )
        assert result is False
        assert voice.status == VoiceStatus.ERROR
        assert voice.allocation_status == VoiceAllocationStatus.RECORDED

    def test_clone_returns_no_voice_id(
        self, monkeypatch, stub_db, stub_events,
    ):
        voice = _make_voice()
        monkeypatch.setattr(
            "models.voice_model.Voice.query",
            SimpleNamespace(get=lambda _id: voice),
        )
        monkeypatch.setattr(
            "models.voice_model.VoiceModel.available_slot_capacity",
            staticmethod(lambda provider=None: 5),
        )
        monkeypatch.setattr(
            "utils.s3_client.S3Client.download_fileobj",
            lambda key: BytesIO(b"audio"),
        )
        monkeypatch.setattr(
            "models.voice_model.VoiceModel._clone_voice_api",
            staticmethod(lambda *a, **kw: (True, {"voice_id": None})),
        )
        monkeypatch.setattr(
            "utils.voice_slot_manager.VoiceSlotManager._release_voice_lock",
            classmethod(lambda cls, vid: None),
        )

        result = allocate_voice_slot.run(
            voice_id=1, s3_key="k", filename="f.wav", user_id=10,
        )
        assert result is False
        assert voice.status == VoiceStatus.ERROR

    def test_voice_not_found_releases_lock(self, monkeypatch, stub_db):
        monkeypatch.setattr(
            "models.voice_model.Voice.query",
            SimpleNamespace(get=lambda _id: None),
        )
        released = []
        monkeypatch.setattr(
            "utils.voice_slot_manager.VoiceSlotManager._release_voice_lock",
            classmethod(lambda cls, vid: released.append(vid)),
        )

        result = allocate_voice_slot.run(
            voice_id=999, s3_key="k", filename="f.wav", user_id=10,
        )
        assert result is False
        assert 999 in released


# ===================================================================
# process_voice_queue
# ===================================================================

class TestProcessVoiceQueue:

    def test_empty_queue_returns_zero(self, monkeypatch, stub_db, stub_queue):
        stub_queue["items"] = []
        monkeypatch.setattr(
            "models.voice_model.Voice.query",
            SimpleNamespace(get=lambda _id: None),
        )

        result = process_voice_queue.run()
        assert result == 0

    def test_dispatches_items_within_capacity(
        self, monkeypatch, stub_db, stub_queue, stub_metrics,
    ):
        stub_queue["items"] = [
            {"voice_id": 1, "s3_key": "k1", "filename": "f1.wav",
             "user_id": 10, "voice_name": "V1", "attempts": 0,
             "service_provider": "elevenlabs"},
            {"voice_id": 2, "s3_key": "k2", "filename": "f2.wav",
             "user_id": 11, "voice_name": "V2", "attempts": 0,
             "service_provider": "elevenlabs"},
        ]

        monkeypatch.setattr(
            "models.voice_model.VoiceModel.available_slot_capacity",
            staticmethod(lambda provider=None: 5),
        )

        dispatched = []
        monkeypatch.setattr(
            "tasks.voice_tasks.allocate_voice_slot.delay",
            lambda **kw: dispatched.append(kw),
        )

        result = process_voice_queue.run()
        assert result == 2
        assert len(dispatched) == 2
        assert dispatched[0]["voice_id"] == 1
        assert dispatched[1]["voice_id"] == 2

    def test_re_enqueues_overflow_when_capacity_partial(
        self, monkeypatch, stub_db, stub_queue, stub_metrics,
    ):
        stub_queue["items"] = [
            {"voice_id": i, "s3_key": f"k{i}", "filename": f"f{i}.wav",
             "user_id": i * 10, "voice_name": f"V{i}", "attempts": 0,
             "service_provider": "elevenlabs"}
            for i in range(1, 5)  # 4 items
        ]

        monkeypatch.setattr(
            "models.voice_model.VoiceModel.available_slot_capacity",
            staticmethod(lambda provider=None: 2),
        )

        dispatched = []
        monkeypatch.setattr(
            "tasks.voice_tasks.allocate_voice_slot.delay",
            lambda **kw: dispatched.append(kw),
        )

        result = process_voice_queue.run()
        assert result == 2
        assert len(dispatched) == 2
        # Overflow re-enqueued
        assert len(stub_queue["enqueued"]) == 2

    def test_zero_capacity_re_enqueues_all(
        self, monkeypatch, stub_db, stub_queue, stub_metrics,
    ):
        stub_queue["items"] = [
            {"voice_id": 1, "s3_key": "k", "filename": "f.wav",
             "user_id": 10, "voice_name": "V", "attempts": 0,
             "service_provider": "elevenlabs"},
        ]

        monkeypatch.setattr(
            "models.voice_model.VoiceModel.available_slot_capacity",
            staticmethod(lambda provider=None: 0),
        )

        result = process_voice_queue.run()
        assert result == 0
        assert len(stub_queue["enqueued"]) == 1

    def test_populates_missing_provider_from_db(
        self, monkeypatch, stub_db, stub_queue, stub_metrics,
    ):
        voice = _make_voice(service_provider="cartesia")
        stub_queue["items"] = [
            {"voice_id": 1, "s3_key": "k", "filename": "f.wav",
             "user_id": 10, "voice_name": "V", "attempts": 0},
        ]

        monkeypatch.setattr(
            "models.voice_model.Voice.query",
            SimpleNamespace(get=lambda _id: voice),
        )
        monkeypatch.setattr(
            "models.voice_model.VoiceModel.available_slot_capacity",
            staticmethod(lambda provider=None: float("inf")),
        )

        dispatched = []
        monkeypatch.setattr(
            "tasks.voice_tasks.allocate_voice_slot.delay",
            lambda **kw: dispatched.append(kw),
        )

        result = process_voice_queue.run()
        assert result == 1
        assert dispatched[0]["service_provider"] == "cartesia"


# ===================================================================
# reclaim_idle_voices
# ===================================================================

class TestReclaimIdleVoices:

    def _patch_query(self, monkeypatch, candidates):
        """Patch Voice.query to return candidates for reclaim queries."""
        class FakeQuery:
            def __init__(self):
                self._candidates = list(candidates)
                self._limit_val = None

            def filter(self, *args, **kwargs):
                return self

            def order_by(self, *args):
                return self

            def limit(self, n):
                self._limit_val = n
                return self

            def all(self):
                if self._limit_val is not None:
                    return self._candidates[:self._limit_val]
                return self._candidates

        monkeypatch.setattr("models.voice_model.Voice.query", FakeQuery())

    def test_evicts_idle_voices_when_queue_has_pressure(
        self, monkeypatch, stub_db, stub_events,
    ):
        stale = datetime.utcnow() - timedelta(hours=2)
        voice = _make_voice(
            allocation_status=VoiceAllocationStatus.READY,
            status=VoiceStatus.READY,
            elevenlabs_voice_id="ext-1",
            last_used_at=stale,
        )

        self._patch_query(monkeypatch, [voice])

        monkeypatch.setattr(
            "tasks.voice_tasks.VoiceSlotQueue.length", lambda: 3,
        )
        monkeypatch.setattr(
            "utils.voice_service.VoiceService.delete_voice",
            lambda **kw: (True, "deleted"),
        )
        monkeypatch.setattr(
            "tasks.voice_tasks.process_voice_queue.delay", lambda: None,
        )

        result = reclaim_idle_voices.run()

        assert result >= 1
        assert voice.allocation_status == VoiceAllocationStatus.RECORDED
        assert voice.elevenlabs_voice_id is None
        assert stub_db.commit_calls >= 1

    def test_no_eviction_when_queue_empty_and_voices_recent(
        self, monkeypatch, stub_db,
    ):
        recent = datetime.utcnow() - timedelta(minutes=5)
        voice = _make_voice(
            allocation_status=VoiceAllocationStatus.READY,
            elevenlabs_voice_id="ext-1",
            last_used_at=recent,
        )

        self._patch_query(monkeypatch, [])
        monkeypatch.setattr("tasks.voice_tasks.VoiceSlotQueue.length", lambda: 0)

        result = reclaim_idle_voices.run()
        assert result == 0

    def test_remote_delete_failure_skips_voice(
        self, monkeypatch, stub_db, stub_events,
    ):
        stale = datetime.utcnow() - timedelta(hours=2)
        voice = _make_voice(
            allocation_status=VoiceAllocationStatus.READY,
            status=VoiceStatus.READY,
            elevenlabs_voice_id="ext-1",
            last_used_at=stale,
        )

        self._patch_query(monkeypatch, [voice])
        monkeypatch.setattr("tasks.voice_tasks.VoiceSlotQueue.length", lambda: 1)
        monkeypatch.setattr(
            "utils.voice_service.VoiceService.delete_voice",
            lambda **kw: (False, "API error"),
        )

        result = reclaim_idle_voices.run()
        # Voice should NOT have been evicted
        assert result == 0
        assert voice.allocation_status == VoiceAllocationStatus.READY


# ===================================================================
# reset_stuck_allocations
# ===================================================================

class TestResetStuckAllocations:

    def _patch_query(self, monkeypatch, stuck_voices):
        class FakeQuery:
            def __init__(self):
                self._voices = list(stuck_voices)

            def filter(self, *args, **kwargs):
                return self

            def order_by(self, *args):
                return self

            def limit(self, n):
                self._voices = self._voices[:n]
                return self

            def all(self):
                return self._voices

        monkeypatch.setattr("models.voice_model.Voice.query", FakeQuery())

    def test_resets_stuck_voices_and_re_enqueues(
        self, monkeypatch, stub_db, stub_events, stub_queue,
    ):
        stuck = _make_voice(
            allocation_status=VoiceAllocationStatus.ALLOCATING,
            status=VoiceStatus.PROCESSING,
            slot_lock_expires_at=datetime.utcnow() - timedelta(minutes=15),
            updated_at=datetime.utcnow() - timedelta(minutes=15),
        )

        self._patch_query(monkeypatch, [stuck])
        monkeypatch.setattr(
            "tasks.voice_tasks.process_voice_queue.delay", lambda: None,
        )

        result = reset_stuck_allocations.run()

        assert result == 1
        assert stuck.status == VoiceStatus.RECORDED
        assert stuck.allocation_status == VoiceAllocationStatus.RECORDED
        assert stuck.slot_lock_expires_at is None
        assert stuck.error_message == "stale_allocation_reset"
        assert len(stub_queue["enqueued"]) == 1
        assert stub_db.commit_calls >= 1

    def test_no_stuck_voices_returns_zero(
        self, monkeypatch, stub_db, stub_queue,
    ):
        self._patch_query(monkeypatch, [])

        result = reset_stuck_allocations.run()
        assert result == 0
        assert stub_db.commit_calls == 0

    def test_respects_max_to_reset(
        self, monkeypatch, stub_db, stub_events, stub_queue,
    ):
        voices = [
            _make_voice(
                id=i,
                allocation_status=VoiceAllocationStatus.ALLOCATING,
                status=VoiceStatus.PROCESSING,
                slot_lock_expires_at=datetime.utcnow() - timedelta(minutes=15),
                updated_at=datetime.utcnow() - timedelta(minutes=15),
            )
            for i in range(1, 6)  # 5 stuck voices
        ]

        self._patch_query(monkeypatch, voices)
        monkeypatch.setattr(
            "tasks.voice_tasks.process_voice_queue.delay", lambda: None,
        )

        result = reset_stuck_allocations.run(max_to_reset=2)
        # Query is limited to 2 by the task
        assert result <= 2


# ===================================================================
# Capacity counting: ALLOCATING voices included
# ===================================================================

class TestCapacityCountsAllocating:
    """Verify that available_slot_capacity includes ALLOCATING voices."""

    def test_allocating_voices_reduce_capacity(self, app):
        from models.voice_model import Voice, VoiceModel, VoiceAllocationStatus
        from models.user_model import User
        from database import db

        with app.app_context():
            # Clean up
            existing = User.query.filter_by(email="capacity@test.com").first()
            if existing:
                Voice.query.filter_by(user_id=existing.id).delete()
                db.session.delete(existing)
                db.session.commit()

            user = User(email="capacity@test.com", is_active=True, email_confirmed=True)
            user.set_password("Password123!")
            db.session.add(user)
            db.session.commit()

            # Create 28 READY voices and 2 ALLOCATING voices = 30 used
            for i in range(28):
                v = Voice(
                    name=f"ready_{i}", user_id=user.id,
                    recording_s3_key=f"key_{i}",
                    status=VoiceStatus.READY,
                    allocation_status=VoiceAllocationStatus.READY,
                    elevenlabs_voice_id=f"ext_{i}",
                    service_provider="elevenlabs",
                )
                db.session.add(v)

            for i in range(2):
                v = Voice(
                    name=f"allocating_{i}", user_id=user.id,
                    recording_s3_key=f"alloc_key_{i}",
                    status=VoiceStatus.PROCESSING,
                    allocation_status=VoiceAllocationStatus.ALLOCATING,
                    service_provider="elevenlabs",
                )
                db.session.add(v)

            db.session.commit()

            capacity = VoiceModel.available_slot_capacity("elevenlabs")
            assert capacity == 0, (
                f"Expected 0 capacity with 28 READY + 2 ALLOCATING = 30 used, got {capacity}"
            )

            # Clean up
            Voice.query.filter_by(user_id=user.id).delete()
            db.session.delete(user)
            db.session.commit()


# ===================================================================
# Distributed lock tests
# ===================================================================

class TestDistributedLock:
    """Verify the per-voice allocation lock prevents duplicate allocations."""

    def test_lock_prevents_duplicate_allocation(self, monkeypatch, stub_events):
        from utils.voice_slot_manager import VoiceSlotManager

        voice = _make_voice()

        # Patch VoiceSlotManager's own db (imported from database, not tasks)
        vsm_session = DummySession()
        monkeypatch.setattr(
            "utils.voice_slot_manager.db",
            SimpleNamespace(session=vsm_session),
        )
        # Skip the real _reload_voice_state which tries db.session.refresh
        monkeypatch.setattr(
            "utils.voice_slot_manager.VoiceSlotManager._reload_voice_state",
            staticmethod(lambda v: v),
        )

        monkeypatch.setattr(
            "utils.voice_slot_manager.VoiceSlotQueue.is_enqueued", lambda *_: False,
        )
        monkeypatch.setattr(
            "utils.voice_slot_manager.VoiceSlotQueue.length", lambda: 0,
        )
        monkeypatch.setattr(
            "utils.voice_slot_manager.VoiceSlotQueue.position", lambda _: None,
        )

        # First call acquires the lock, second call fails (lock held)
        lock_acquired = [True, False]
        call_count = [0]

        def mock_set(key, value, nx=False, ex=None):
            idx = call_count[0]
            call_count[0] += 1
            return lock_acquired[idx] if idx < len(lock_acquired) else False

        mock_redis = MagicMock()
        mock_redis.set = mock_set
        mock_redis.delete = MagicMock()

        monkeypatch.setattr(
            "utils.voice_slot_manager.RedisClient.get_client", lambda: mock_redis,
        )
        monkeypatch.setattr(
            "models.voice_model.VoiceModel.available_slot_capacity",
            staticmethod(lambda provider=None: 5),
        )
        task_stub = MagicMock()
        task_stub.delay.return_value = MagicMock(id="task-1")
        monkeypatch.setattr("tasks.voice_tasks.allocate_voice_slot", task_stub)

        # First allocation succeeds
        state1 = VoiceSlotManager.ensure_active_voice(voice)
        assert state1.status == VoiceSlotManager.STATUS_ALLOCATING

        # Reset voice state to simulate concurrent request
        voice2 = _make_voice()

        # Second allocation blocked by lock
        state2 = VoiceSlotManager.ensure_active_voice(voice2)
        assert state2.status == VoiceSlotManager.STATUS_ALLOCATING
        # Task should only be dispatched once
        assert task_stub.delay.call_count == 1
