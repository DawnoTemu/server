import os
import threading
from typing import Optional

import redis


class RedisClient:
    """Singleton Redis client accessor."""

    _client: Optional[redis.Redis] = None
    _lock = threading.Lock()

    @classmethod
    def get_client(cls) -> redis.Redis:
        if cls._client is None:
            with cls._lock:
                if cls._client is None:
                    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
                    cls._client = redis.Redis.from_url(url, decode_responses=True)
        return cls._client

