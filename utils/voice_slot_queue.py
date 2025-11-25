import json
import logging
import time
from typing import Any, Dict, Optional

from utils.redis_client import RedisClient


logger = logging.getLogger(__name__)


class VoiceSlotQueue:
    """Redis-backed queue for voice slot allocation requests."""

    QUEUE_KEY = "voice_slots:queue"
    DETAILS_KEY = "voice_slots:details"

    @classmethod
    def enqueue(cls, voice_id: int, payload: Dict[str, Any], delay_seconds: int = 0) -> None:
        client = RedisClient.get_client()
        score = time.time() + max(delay_seconds, 0)
        voice_key = str(voice_id)
        serialized = json.dumps({**payload, "voice_id": voice_id})
        with client.pipeline() as pipe:
            pipe.hset(cls.DETAILS_KEY, voice_key, serialized)
            pipe.zadd(cls.QUEUE_KEY, {voice_key: score})
            pipe.execute()
        logger.info("Voice %s queued for allocation (score=%s)", voice_id, score)

    @classmethod
    def dequeue(cls) -> Optional[Dict[str, Any]]:
        client = RedisClient.get_client()
        now = time.time()

        while True:
            candidates = client.zrangebyscore(
                cls.QUEUE_KEY,
                '-inf',
                now,
                start=0,
                num=1,
                withscores=True,
            )
            if not candidates:
                return None

            voice_key, score = candidates[0]
            with client.pipeline() as pipe:
                pipe.zrem(cls.QUEUE_KEY, voice_key)
                pipe.hget(cls.DETAILS_KEY, voice_key)
                pipe.hdel(cls.DETAILS_KEY, voice_key)
                removed, data, _ = pipe.execute()

            if removed == 0:
                # Another worker claimed this entry; try the next candidate (if any)
                continue

            if data is None:
                logger.warning("Queue entry %s (score=%s) missing payload; skipping", voice_key, score)
                continue

            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                logger.exception("Failed to decode payload for voice %s; skipping", voice_key)
                continue

            return payload

    @classmethod
    def dequeue_ready_batch(cls, limit: int = 10) -> list[Dict[str, Any]]:
        """Pop up to `limit` ready entries in order and return their payloads."""
        client = RedisClient.get_client()
        now = time.time()
        if limit <= 0:
            return []

        keys = client.zrangebyscore(
            cls.QUEUE_KEY,
            '-inf',
            now,
            start=0,
            num=limit,
        )
        if not keys:
            return []

        results: list[Dict[str, Any]] = []
        for voice_key in keys:
            with client.pipeline() as pipe:
                pipe.zrem(cls.QUEUE_KEY, voice_key)
                pipe.hget(cls.DETAILS_KEY, voice_key)
                pipe.hdel(cls.DETAILS_KEY, voice_key)
                removed, data, _ = pipe.execute()

            if removed == 0 or data is None:
                continue

            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                logger.exception("Failed to decode payload for voice %s; skipping", voice_key)
                continue

            results.append(payload)

        return results

    @classmethod
    def remove(cls, voice_id: int) -> None:
        client = RedisClient.get_client()
        voice_key = str(voice_id)
        with client.pipeline() as pipe:
            pipe.zrem(cls.QUEUE_KEY, voice_key)
            pipe.hdel(cls.DETAILS_KEY, voice_key)
            pipe.execute()

    @classmethod
    def length(cls) -> int:
        client = RedisClient.get_client()
        return int(client.zcard(cls.QUEUE_KEY))

    @classmethod
    def peek(cls) -> Optional[Dict[str, Any]]:
        client = RedisClient.get_client()
        result = client.zrange(cls.QUEUE_KEY, 0, 0)
        if not result:
            return None
        data = client.hget(cls.DETAILS_KEY, result[0])
        return json.loads(data) if data else None

    @classmethod
    def is_enqueued(cls, voice_id: int) -> bool:
        """Check if a given voice already has a queued allocation request."""
        client = RedisClient.get_client()
        return bool(client.hexists(cls.DETAILS_KEY, str(voice_id)))

    @classmethod
    def position(cls, voice_id: int) -> Optional[int]:
        """Return the zero-based position of a queued voice, or None if it is not queued."""
        client = RedisClient.get_client()
        rank = client.zrank(cls.QUEUE_KEY, str(voice_id))
        return int(rank) if rank is not None else None

    @classmethod
    def snapshot(cls, limit: int = 50) -> list[Dict[str, Any]]:
        """Return queued requests ordered by score, capped at limit entries."""
        client = RedisClient.get_client()
        if limit == 0:
            return []
        if limit is None or limit < 0:
            limit = -1
            end_index = -1
        else:
            end_index = limit - 1
        raw = client.zrange(cls.QUEUE_KEY, 0, end_index if end_index >= 0 else -1, withscores=True)
        entries = []
        for member, score in raw:
            data = client.hget(cls.DETAILS_KEY, member)
            payload = json.loads(data) if data else {"voice_id": int(member)}
            payload["score"] = score
            entries.append(payload)
        return entries
