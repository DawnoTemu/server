"""
Helper utilities for load tests: authentication, polling, data setup,
and Redis monitoring.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

try:
    import redis
except ImportError:
    redis = None  # type: ignore[assignment]

from tests.load.config import (
    ADMIN_API_KEY,
    REDIS_CELERY_QUEUE_KEY,
    REDIS_SYNTH_CONCURRENCY_KEY,
    REDIS_VOICE_QUEUE_KEY,
    S2_POLL_INTERVAL_SEC,
    S2_POLL_TIMEOUT_SEC,
    TEST_USER_EMAIL_TEMPLATE,
    TEST_USER_PASSWORD,
)

logger = logging.getLogger("loadtest.helpers")


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

@dataclass
class AuthTokens:
    access_token: str
    refresh_token: str
    user_id: int


def login_user(client, email: str, password: str) -> Optional[AuthTokens]:
    """Log in a user via POST /auth/login and return tokens."""
    resp = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        name="/auth/login",
    )
    if resp.status_code != 200:
        logger.error("Login failed for %s: %s %s", email, resp.status_code, resp.text)
        return None
    data = resp.json()
    return AuthTokens(
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        user_id=data["user"]["id"],
    )


def refresh_access_token(client, refresh_token: str) -> Optional[str]:
    """Refresh an access token via POST /auth/refresh."""
    resp = client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token},
        name="/auth/refresh",
    )
    if resp.status_code != 200:
        logger.error("Token refresh failed: %s %s", resp.status_code, resp.text)
        return None
    return resp.json().get("access_token")


def auth_headers(access_token: str) -> dict:
    """Return Authorization header dict."""
    return {"Authorization": f"Bearer {access_token}"}


def make_test_email(n: int) -> str:
    """Generate the n-th test user email."""
    return TEST_USER_EMAIL_TEMPLATE.format(n=n)


# ---------------------------------------------------------------------------
# Polling helpers
# ---------------------------------------------------------------------------

@dataclass
class PollResult:
    """Result of a polling loop."""
    success: bool
    final_status: str = ""
    elapsed_sec: float = 0.0
    polls: int = 0
    error: str = ""


def poll_audio_ready(
    client,
    voice_id,
    story_id,
    access_token: str,
    interval: float = S2_POLL_INTERVAL_SEC,
    timeout: float = S2_POLL_TIMEOUT_SEC,
) -> PollResult:
    """
    Poll HEAD /voices/{voice_id}/stories/{story_id}/audio until 200 (ready)
    or timeout. Reports total generation time as a Locust request metric.
    """
    start = time.monotonic()
    polls = 0
    url = f"/voices/{voice_id}/stories/{story_id}/audio"

    while True:
        elapsed = time.monotonic() - start
        if elapsed >= timeout:
            return PollResult(
                success=False,
                final_status="timeout",
                elapsed_sec=elapsed,
                polls=polls,
                error=f"Timed out after {timeout}s",
            )

        resp = client.head(
            url,
            headers=auth_headers(access_token),
            name="HEAD /voices/[id]/stories/[id]/audio",
        )
        polls += 1

        if resp.status_code == 200:
            elapsed = time.monotonic() - start
            return PollResult(
                success=True,
                final_status="ready",
                elapsed_sec=elapsed,
                polls=polls,
            )

        if resp.status_code not in (404, 202):
            # Unexpected status — keep polling but log it
            logger.warning("Unexpected HEAD status %s for %s", resp.status_code, url)

        time.sleep(interval)


# ---------------------------------------------------------------------------
# Synthesis request helper
# ---------------------------------------------------------------------------

@dataclass
class SynthResult:
    """Result of a POST synthesis request."""
    success: bool
    status_code: int = 0
    audio_id: Optional[int] = None
    response_status: str = ""
    error: str = ""


def request_synthesis(
    client,
    voice_id,
    story_id,
    access_token: str,
) -> SynthResult:
    """
    POST /voices/{voice_id}/stories/{story_id}/audio to start synthesis.
    """
    resp = client.post(
        f"/voices/{voice_id}/stories/{story_id}/audio",
        headers=auth_headers(access_token),
        name="POST /voices/[id]/stories/[id]/audio",
    )
    if resp.status_code in (200, 202):
        data = resp.json()
        return SynthResult(
            success=True,
            status_code=resp.status_code,
            audio_id=data.get("id"),
            response_status=data.get("status", ""),
        )
    return SynthResult(
        success=False,
        status_code=resp.status_code,
        error=resp.text[:500],
    )


# ---------------------------------------------------------------------------
# Redis monitoring
# ---------------------------------------------------------------------------

@dataclass
class RedisMetrics:
    celery_queue_depth: int = 0
    synth_concurrency: int = 0
    voice_queue_depth: int = 0


def get_redis_metrics(redis_url: str = "redis://localhost:6379/0") -> RedisMetrics:
    """Read current queue depths and concurrency counters from Redis."""
    if redis is None:
        logger.warning("redis package not available — skipping metrics")
        return RedisMetrics()
    try:
        r = redis.from_url(redis_url, decode_responses=True)
        return RedisMetrics(
            celery_queue_depth=r.llen(REDIS_CELERY_QUEUE_KEY),
            synth_concurrency=int(r.get(REDIS_SYNTH_CONCURRENCY_KEY) or 0),
            voice_queue_depth=r.zcard(REDIS_VOICE_QUEUE_KEY),
        )
    except Exception as exc:
        logger.error("Failed to read Redis metrics: %s", exc)
        return RedisMetrics()


# ---------------------------------------------------------------------------
# Test data setup (for admin/scripted setup, not run during load tests)
# ---------------------------------------------------------------------------

def setup_test_users(client, count: int, admin_key: str = ADMIN_API_KEY):
    """
    Create test users via API. Requires admin privileges.
    Returns a list of (email, password) tuples.

    This is a setup utility — call it before running load tests,
    not as part of the load test itself.
    """
    users = []
    for n in range(1, count + 1):
        email = make_test_email(n)
        resp = client.post(
            "/auth/register",
            json={
                "email": email,
                "password": TEST_USER_PASSWORD,
                "password_confirm": TEST_USER_PASSWORD,
            },
        )
        if resp.status_code in (200, 201, 409):
            # 409 = already exists, which is fine
            users.append((email, TEST_USER_PASSWORD))
        else:
            logger.error(
                "Failed to create user %s: %s %s",
                email,
                resp.status_code,
                resp.text,
            )
    return users


def activate_test_users(base_url: str, count: int, admin_token: str = ADMIN_API_KEY):
    """
    Activate test users via the admin API.

    Requires a valid admin JWT token (from /admin/auth/generate-token).
    The endpoint is POST /admin/users/<user_id>/activate with @admin_required.

    For local Docker testing, prefer tests.load.setup_test_data which
    creates users already activated, bypassing HTTP auth entirely.
    """
    import requests as req

    headers = {"Authorization": f"Bearer {admin_token}"}
    activated = 0
    for n in range(1, count + 1):
        email = make_test_email(n)
        # First look up user ID by email via admin list
        list_resp = req.get(
            f"{base_url}/admin/users",
            headers=headers,
            timeout=10,
        )
        if list_resp.status_code != 200:
            logger.error("Could not list users: %s", list_resp.status_code)
            break
        users = list_resp.json().get("users", [])
        user = next((u for u in users if u.get("email") == email), None)
        if not user:
            logger.warning("User %s not found in admin list", email)
            continue
        resp = req.post(
            f"{base_url}/admin/users/{user['id']}/activate",
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 200:
            activated += 1
        else:
            logger.warning("Could not activate %s: %s", email, resp.status_code)
    logger.info("Activated %d / %d test users", activated, count)
    return activated
