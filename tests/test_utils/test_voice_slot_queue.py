from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import pytest

from utils.voice_slot_queue import VoiceSlotQueue


class FakeRedis:
    def __init__(self) -> None:
        self.sorted_sets: Dict[str, Dict[str, float]] = defaultdict(dict)
        self.hashes: Dict[str, Dict[str, str]] = defaultdict(dict)

    # -- Sorted set helpers -------------------------------------------------
    def zadd(self, key: str, mapping: Dict[str, float]) -> int:
        added = 0
        for member, score in mapping.items():
            member = str(member)
            if member not in self.sorted_sets[key]:
                added += 1
            self.sorted_sets[key][member] = float(score)
        return added

    def zrange(
        self,
        key: str,
        start: int,
        end: int,
        withscores: bool = False,
    ) -> List[Any]:
        values = self._sorted_members(key)
        start_idx, end_idx = self._translate_slice(len(values), start, end)
        sliced = values[start_idx:end_idx]
        if withscores:
            return [(member, score) for member, score in sliced]
        return [member for member, _ in sliced]

    def zrangebyscore(
        self,
        key: str,
        min_score: Any,
        max_score: Any,
        start: Optional[int] = None,
        num: Optional[int] = None,
        withscores: bool = False,
    ) -> List[Any]:
        min_value = self._parse_score(min_score)
        max_value = self._parse_score(max_score)
        values = [
            (member, score)
            for member, score in self._sorted_members(key)
            if min_value <= score <= max_value
        ]
        offset = start or 0
        if offset:
            values = values[offset:]
        if num is not None:
            values = values[:num]
        if withscores:
            return values
        return [member for member, _ in values]

    def zrem(self, key: str, member: str) -> int:
        member = str(member)
        if member in self.sorted_sets[key]:
            del self.sorted_sets[key][member]
            return 1
        return 0

    def zcard(self, key: str) -> int:
        return len(self.sorted_sets[key])

    def zrank(self, key: str, member: str) -> Optional[int]:
        members = [m for m, _ in self._sorted_members(key)]
        try:
            return members.index(str(member))
        except ValueError:
            return None

    # -- Hash helpers -------------------------------------------------------
    def hset(self, key: str, field: str, value: str) -> int:
        field = str(field)
        is_new = field not in self.hashes[key]
        self.hashes[key][field] = value
        return 1 if is_new else 0

    def hget(self, key: str, field: str) -> Optional[str]:
        return self.hashes[key].get(str(field))

    def hdel(self, key: str, field: str) -> int:
        field = str(field)
        if field in self.hashes[key]:
            del self.hashes[key][field]
            return 1
        return 0

    def hexists(self, key: str, field: str) -> bool:
        return str(field) in self.hashes[key]

    # -- Pipeline -----------------------------------------------------------
    def pipeline(self):
        return FakePipeline(self)

    # -- Internal utilities -------------------------------------------------
    def _sorted_members(self, key: str) -> List[Tuple[str, float]]:
        items = list(self.sorted_sets[key].items())
        items.sort(key=lambda item: (item[1], item[0]))
        return items

    @staticmethod
    def _parse_score(value: Any) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            if value in ("-inf", "-infinity"):
                return float("-inf")
            if value in ("+inf", "inf", "+infinity", "infinity"):
                return float("inf")
            if value.startswith("("):
                # Exclusive bounds; drop the leading "(" and treat as float
                return float(value[1:])
            return float(value)
        raise TypeError(f"Unsupported score bound: {value!r}")

    @staticmethod
    def _translate_slice(length: int, start: int, end: int) -> Tuple[int, int]:
        if start < 0:
            start = max(length + start, 0)
        if end < 0:
            end = length + end + 1
        else:
            end += 1
        return max(start, 0), min(end, length)


class FakePipeline:
    def __init__(self, client: FakeRedis) -> None:
        self.client = client
        self._results: List[Any] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self._results.clear()
        # Allow exceptions to propagate
        return False

    # Proxy methods that collect results -----------------------------------
    def hset(self, *args, **kwargs):
        result = self.client.hset(*args, **kwargs)
        self._results.append(result)
        return self

    def zadd(self, *args, **kwargs):
        result = self.client.zadd(*args, **kwargs)
        self._results.append(result)
        return self

    def zrem(self, *args, **kwargs):
        result = self.client.zrem(*args, **kwargs)
        self._results.append(result)
        return self

    def hget(self, *args, **kwargs):
        result = self.client.hget(*args, **kwargs)
        self._results.append(result)
        return self

    def hdel(self, *args, **kwargs):
        result = self.client.hdel(*args, **kwargs)
        self._results.append(result)
        return self

    def execute(self):
        results = list(self._results)
        self._results.clear()
        return results


class FakeClock:
    def __init__(self, start: float) -> None:
        self._now = start

    def time(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


@pytest.fixture
def fake_redis(monkeypatch) -> FakeRedis:
    client = FakeRedis()
    monkeypatch.setattr("utils.voice_slot_queue.RedisClient.get_client", lambda: client)
    return client


@pytest.fixture
def fake_clock(monkeypatch) -> FakeClock:
    clock = FakeClock(1_000.0)
    monkeypatch.setattr("utils.voice_slot_queue.time.time", clock.time)
    return clock


def test_dequeue_respects_delay(fake_redis, fake_clock):
    VoiceSlotQueue.enqueue(voice_id=101, payload={"attempts": 1}, delay_seconds=30)

    # Not ready yet -> should not be dequeued
    assert VoiceSlotQueue.dequeue() is None
    assert VoiceSlotQueue.length() == 1

    # Advance beyond delay
    fake_clock.advance(35)
    payload = VoiceSlotQueue.dequeue()
    assert payload["voice_id"] == 101
    assert payload["attempts"] == 1
    assert VoiceSlotQueue.length() == 0


def test_dequeue_skips_future_entries_and_returns_ready(fake_redis, fake_clock):
    VoiceSlotQueue.enqueue(voice_id=301, payload={"state": "future"}, delay_seconds=60)
    VoiceSlotQueue.enqueue(voice_id=302, payload={"state": "ready"}, delay_seconds=0)

    payload = VoiceSlotQueue.dequeue()
    assert payload["voice_id"] == 302
    assert payload["state"] == "ready"

    # Future entry still pending
    assert VoiceSlotQueue.dequeue() is None

    fake_clock.advance(65)
    payload_later = VoiceSlotQueue.dequeue()
    assert payload_later["voice_id"] == 301
    assert payload_later["state"] == "future"


def test_snapshot_zero_limit_returns_empty(fake_redis):
    VoiceSlotQueue.enqueue(voice_id=401, payload={"meta": "a"})
    VoiceSlotQueue.enqueue(voice_id=402, payload={"meta": "b"})

    assert VoiceSlotQueue.snapshot(limit=0) == []
