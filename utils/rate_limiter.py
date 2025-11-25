import time
from functools import wraps
from typing import Callable, Dict, Optional, Tuple

from flask import request, jsonify, current_app


_REQUEST_LOG: Dict[Tuple[str, str], list] = {}


def rate_limit(limit: int = 10, window_seconds: int = 60, key_func: Optional[Callable[[], str]] = None):
    """
    Simple in-memory rate limiter. Use for lightweight protection of sensitive endpoints.
    Not suitable for multi-process production without a shared backend.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key_source = key_func() if key_func else request.remote_addr or "unknown"
            if current_app and current_app.config.get("TESTING"):
                return func(*args, **kwargs)
            now = time.time()
            window_start = now - window_seconds

            bucket = _REQUEST_LOG.setdefault((func.__name__, key_source), [])
            # Drop old entries
            while bucket and bucket[0] < window_start:
                bucket.pop(0)

            if len(bucket) >= limit:
                return jsonify({"error": "Too many requests, please slow down"}), 429

            bucket.append(now)
            return func(*args, **kwargs)

        return wrapper

    return decorator
