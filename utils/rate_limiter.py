import logging

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

logger = logging.getLogger("rate_limiter")

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri="memory://",
)
