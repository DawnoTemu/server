import logging
from contextlib import contextmanager
from typing import Optional

from utils.redis_client import RedisClient

logger = logging.getLogger("concurrency_limiter")


class ConcurrencyLimitExceeded(Exception):
    """Raised when a concurrency slot cannot be acquired."""


class ConcurrencyLimiter:
    """Redis-backed guard to cap concurrent operations across workers."""

    KEY_TEMPLATE = "concurrency:{name}"

    _ACQUIRE_SCRIPT = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
local current = tonumber(redis.call("get", key) or "0")
if current >= limit then
  return {0, current}
end
current = redis.call("incr", key)
redis.call("expire", key, ttl)
return {1, current}
"""

    _RELEASE_SCRIPT = """
local key = KEYS[1]
local current = tonumber(redis.call("get", key) or "0")
if current <= 1 then
  redis.call("del", key)
  return 0
end
return redis.call("decr", key)
"""

    @classmethod
    def _key(cls, name: str) -> str:
        return cls.KEY_TEMPLATE.format(name=name)

    @classmethod
    def acquire(cls, name: str, *, limit: int, ttl: int = 180) -> bool:
        """
        Attempt to acquire a concurrency slot.

        Returns True when acquired; False when limit is reached.
        """
        if limit is None or limit <= 0:
            return True

        client = RedisClient.get_client()
        key = cls._key(name)
        try:
            result = client.eval(cls._ACQUIRE_SCRIPT, 1, key, int(limit), int(ttl))
            success = int(result[0]) == 1
            current = int(result[1]) if len(result) > 1 else 0
            if not success:
                logger.info(
                    "Concurrency limit reached for %s (current=%s, limit=%s)",
                    name,
                    current,
                    limit,
                )
            else:
                logger.debug(
                    "Acquired concurrency slot for %s (current=%s, limit=%s)",
                    name,
                    current,
                    limit,
                )
            return success
        except Exception as exc:
            logger.exception("Failed to acquire concurrency slot for %s: %s", name, exc)
            raise

    @classmethod
    def release(cls, name: str) -> None:
        """Release a previously acquired slot."""
        client = RedisClient.get_client()
        key = cls._key(name)
        try:
            client.eval(cls._RELEASE_SCRIPT, 1, key)
        except Exception as exc:
            logger.exception("Failed to release concurrency slot for %s: %s", name, exc)

    @classmethod
    @contextmanager
    def guard(cls, name: str, *, limit: Optional[int], ttl: int = 180):
        """
        Context manager that acquires and releases a slot.

        Raises ConcurrencyLimitExceeded when the limit is reached.
        """
        if limit is None or limit <= 0:
            yield
            return

        acquired = cls.acquire(name, limit=limit, ttl=ttl)
        if not acquired:
            raise ConcurrencyLimitExceeded(f"Concurrency limit reached for {name}")

        try:
            yield
        finally:
            cls.release(name)
