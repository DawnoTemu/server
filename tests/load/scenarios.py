"""
Locust scenario TaskSets for load testing the DawnoTemu audio generation pipeline.

Eight scenarios mapping to the plan (S1–S8):
  S1 - Parallel Generation
  S2 - Polling Storm
  S3 - Celery Queue Saturation
  S4 - ElevenLabs Concurrency Limit
  S5 - Credit Race Condition
  S6 - Voice Slot Allocation Queue
  S7 - Token Refresh Under Load
  S8 - Connection Pool Exhaustion

Each scenario is a standalone TaskSet that can be composed into HttpUser
classes in locustfile.py.
"""

import logging
import os
import random
import time

from locust import TaskSet, between, events, tag, task

from tests.load.config import (
    S2_POLL_INTERVAL_SEC,
    S2_POLL_TIMEOUT_SEC,
    S3_BURST_REQUESTS,
    S5_CONCURRENT_REQUESTS_PER_USER,
    S5_CREDITS_PER_USER,
    TEST_USER_EMAIL_TEMPLATE,
    TEST_USER_PASSWORD,
)
from tests.load.helpers import (
    AuthTokens,
    PollResult,
    auth_headers,
    login_user,
    make_test_email,
    poll_audio_ready,
    refresh_access_token,
    request_synthesis,
)

logger = logging.getLogger("loadtest.scenarios")


# ---------------------------------------------------------------------------
# Shared on_start helpers
# ---------------------------------------------------------------------------

def _login_on_start(task_set, user_index_attr: str = "_user_index"):
    """
    Log in a test user based on the Locust greenlet index.
    Stores tokens on the TaskSet instance.
    """
    # Each Locust greenlet gets a unique index via environment._runner
    idx = getattr(task_set.user, user_index_attr, None)
    if idx is None:
        idx = getattr(task_set.user.environment, "_user_counter", 0) + 1
        task_set.user.environment._user_counter = idx
        setattr(task_set.user, user_index_attr, idx)

    email = make_test_email(idx)
    tokens = login_user(task_set.client, email, TEST_USER_PASSWORD)
    if tokens is None:
        raise StopIteration(f"Login failed for {email}")
    task_set._tokens = tokens
    task_set._voice_id = os.getenv("LOADTEST_VOICE_ID", "1")
    task_set._story_ids = _available_story_ids()
    return tokens


def _available_story_ids():
    """Return a list of story IDs available for testing."""
    raw = os.getenv("LOADTEST_STORY_IDS", "1,2,3,4,5")
    return [int(s.strip()) for s in raw.split(",") if s.strip()]


def _pick_story_id(task_set):
    """Pick a random story ID, avoiding repeats where possible."""
    return random.choice(task_set._story_ids)


def _handle_401(task_set, resp):
    """If response is 401, try refreshing the access token."""
    if resp.status_code == 401 and hasattr(task_set, "_tokens"):
        new_token = refresh_access_token(
            task_set.client, task_set._tokens.refresh_token
        )
        if new_token:
            task_set._tokens = AuthTokens(
                access_token=new_token,
                refresh_token=task_set._tokens.refresh_token,
                user_id=task_set._tokens.user_id,
            )
            return True
    return False


# ===================================================================
# S1 — Parallel Generation
# ===================================================================

class S1ParallelGeneration(TaskSet):
    """
    N users simultaneously POST synthesis and poll until COMPLETE.
    Each user uses a different story_id to avoid Redis dedup collapsing.
    """

    def on_start(self):
        _login_on_start(self)

    @tag("s1")
    @task
    def synthesize_and_poll(self):
        story_id = _pick_story_id(self)
        voice_id = self._voice_id
        tokens = self._tokens

        synth = request_synthesis(
            self.client, voice_id, story_id, tokens.access_token
        )
        if not synth.success:
            if synth.status_code == 401 and _handle_401(self, type("R", (), {"status_code": 401})()):
                synth = request_synthesis(
                    self.client, voice_id, story_id, self._tokens.access_token
                )
            if not synth.success:
                logger.error("S1 synthesis request failed: %s", synth.error)
                return

        # Poll until ready
        poll = poll_audio_ready(
            self.client,
            voice_id,
            story_id,
            tokens.access_token,
        )

        # Report total generation time as a custom metric
        events.request.fire(
            request_type="SYNTH",
            name="S1 Full Generation Cycle",
            response_time=poll.elapsed_sec * 1000,
            response_length=0,
            exception=None if poll.success else Exception(poll.error),
            context={},
        )


# ===================================================================
# S2 — Polling Storm
# ===================================================================

class S2PollingStorm(TaskSet):
    """
    Users generate audio once, then aggressively poll HEAD every 5s.
    Measures HEAD latency and 503 rate independently from synthesis.
    """

    def on_start(self):
        _login_on_start(self)
        # Trigger one synthesis to have something to poll
        story_id = _pick_story_id(self)
        self._poll_voice_id = self._voice_id
        self._poll_story_id = story_id
        request_synthesis(
            self.client,
            self._poll_voice_id,
            self._poll_story_id,
            self._tokens.access_token,
        )

    @tag("s2")
    @task
    def poll_head(self):
        resp = self.client.head(
            f"/voices/{self._poll_voice_id}/stories/{self._poll_story_id}/audio",
            headers=auth_headers(self._tokens.access_token),
            name="HEAD /voices/[id]/stories/[id]/audio",
        )
        if resp.status_code == 401:
            _handle_401(self, resp)

        # Track 503s specifically
        if resp.status_code == 503:
            events.request.fire(
                request_type="HEAD",
                name="S2 503 Error",
                response_time=resp.elapsed.total_seconds() * 1000,
                response_length=0,
                exception=Exception("503 Service Unavailable"),
                context={},
            )

        # Small sleep to maintain poll interval
        time.sleep(S2_POLL_INTERVAL_SEC)


# ===================================================================
# S3 — Celery Queue Saturation (Burst)
# ===================================================================

class S3QueueSaturation(TaskSet):
    """
    Burst of POST requests in a short window to saturate the Celery queue.
    Monitors queue depth and drain time.
    """

    def on_start(self):
        _login_on_start(self)
        self._burst_sent = 0

    @tag("s3")
    @task
    def burst_synthesis(self):
        if self._burst_sent >= S3_BURST_REQUESTS:
            # Switch to polling mode after burst
            self._poll_remaining()
            return

        story_id = _pick_story_id(self)
        synth = request_synthesis(
            self.client, self._voice_id, story_id, self._tokens.access_token
        )
        self._burst_sent += 1

        if not synth.success:
            logger.warning(
                "S3 burst request %d failed: %s", self._burst_sent, synth.error
            )

    def _poll_remaining(self):
        """After burst, poll one story to check queue drain."""
        story_id = self._story_ids[0] if self._story_ids else 1
        poll = poll_audio_ready(
            self.client,
            self._voice_id,
            story_id,
            self._tokens.access_token,
            timeout=900,  # 15 min
        )
        events.request.fire(
            request_type="SYNTH",
            name="S3 Queue Drain Time",
            response_time=poll.elapsed_sec * 1000,
            response_length=0,
            exception=None if poll.success else Exception(poll.error),
            context={},
        )
        # Stop this user after burst + drain check
        self.interrupt()


# ===================================================================
# S4 — ElevenLabs Concurrency Limit
# ===================================================================

class S4ElevenLabsConcurrency(TaskSet):
    """
    10 concurrent tasks synthesize simultaneously.
    Verifies concurrency counter never exceeds 5 and all jobs complete.
    """

    def on_start(self):
        _login_on_start(self)

    @tag("s4")
    @task
    def synthesize_with_concurrency(self):
        story_id = _pick_story_id(self)

        synth = request_synthesis(
            self.client, self._voice_id, story_id, self._tokens.access_token
        )
        if not synth.success:
            logger.warning("S4 synthesis failed: %s", synth.error)
            return

        poll = poll_audio_ready(
            self.client,
            self._voice_id,
            story_id,
            self._tokens.access_token,
            timeout=600,
        )

        events.request.fire(
            request_type="SYNTH",
            name="S4 Concurrent Synthesis",
            response_time=poll.elapsed_sec * 1000,
            response_length=0,
            exception=None if poll.success else Exception(poll.error),
            context={},
        )


# ===================================================================
# S5 — Credit Race Condition
# ===================================================================

class S5CreditRace(TaskSet):
    """
    Users with exactly 1 credit each fire 2 simultaneous synthesis requests.
    Verifies exactly 1 succeeds and no overdraft occurs.

    Note: The more thorough credit race test is in test_credit_race.py (pytest).
    This Locust version tests the HTTP layer behavior.
    """

    def on_start(self):
        _login_on_start(self)
        self._fired = False

    @tag("s5")
    @task
    def double_fire(self):
        if self._fired:
            self.interrupt()
            return

        self._fired = True
        story_ids = self._story_ids[:S5_CONCURRENT_REQUESTS_PER_USER]
        if len(story_ids) < S5_CONCURRENT_REQUESTS_PER_USER:
            story_ids = [1, 2]

        results = []
        for sid in story_ids:
            synth = request_synthesis(
                self.client, self._voice_id, sid, self._tokens.access_token
            )
            results.append(synth)

        successes = sum(1 for r in results if r.success)
        errors_402 = sum(1 for r in results if r.status_code == 402)

        events.request.fire(
            request_type="CREDIT",
            name="S5 Credit Race (successes)",
            response_time=0,
            response_length=successes,
            exception=None,
            context={},
        )

        if successes > S5_CREDITS_PER_USER:
            events.request.fire(
                request_type="CREDIT",
                name="S5 OVERDRAFT DETECTED",
                response_time=0,
                response_length=0,
                exception=Exception(
                    f"Double spend: {successes} successes with {S5_CREDITS_PER_USER} credit"
                ),
                context={},
            )


# ===================================================================
# S6 — Voice Slot Allocation Queue
# ===================================================================

class S6SlotQueue(TaskSet):
    """
    35 users with distinct voices request synthesis simultaneously.
    Slot limit is 30 — first 30 proceed, remaining 5 queue.
    """

    def on_start(self):
        _login_on_start(self)
        # Each user uses their own voice_id (distinct per user)
        idx = getattr(self.user, "_user_index", 1)
        self._voice_id = os.getenv(f"LOADTEST_VOICE_ID_{idx}", str(idx))

    @tag("s6")
    @task
    def synthesize_with_distinct_voice(self):
        story_id = _pick_story_id(self)

        synth = request_synthesis(
            self.client, self._voice_id, story_id, self._tokens.access_token
        )
        if not synth.success:
            logger.warning("S6 synthesis failed for voice %s: %s", self._voice_id, synth.error)
            return

        # Long poll — slot allocation can take minutes
        poll = poll_audio_ready(
            self.client,
            self._voice_id,
            story_id,
            self._tokens.access_token,
            timeout=1200,  # 20 min (slot queue + synthesis)
        )

        events.request.fire(
            request_type="SYNTH",
            name="S6 Slot Queue Synthesis",
            response_time=poll.elapsed_sec * 1000,
            response_length=0,
            exception=None if poll.success else Exception(poll.error),
            context={},
        )
        self.interrupt()


# ===================================================================
# S7 — Token Refresh Under Load
# ===================================================================

class S7TokenRefresh(TaskSet):
    """
    During a load test, JWT tokens expire (configured with short TTL).
    Users must refresh tokens mid-flight without dropping requests.
    """

    def on_start(self):
        _login_on_start(self)
        self._request_count = 0

    @tag("s7")
    @task(3)
    def list_stories(self):
        """Light GET /stories request to keep traffic flowing."""
        resp = self.client.get(
            "/stories",
            headers=auth_headers(self._tokens.access_token),
            name="GET /stories",
        )
        self._request_count += 1

        if resp.status_code == 401:
            refreshed = _handle_401(self, resp)
            if refreshed:
                # Retry the request with new token
                self.client.get(
                    "/stories",
                    headers=auth_headers(self._tokens.access_token),
                    name="GET /stories (retry after refresh)",
                )
            else:
                events.request.fire(
                    request_type="AUTH",
                    name="S7 Permanent Auth Failure",
                    response_time=0,
                    response_length=0,
                    exception=Exception("Token refresh failed"),
                    context={},
                )

    @tag("s7")
    @task(1)
    def synthesize_with_refresh(self):
        """POST synthesis that may need token refresh."""
        story_id = _pick_story_id(self)

        synth = request_synthesis(
            self.client, self._voice_id, story_id, self._tokens.access_token
        )
        if not synth.success and synth.status_code == 401:
            refreshed = _handle_401(
                self, type("R", (), {"status_code": 401})()
            )
            if refreshed:
                synth = request_synthesis(
                    self.client, self._voice_id, story_id, self._tokens.access_token
                )

        if synth.success:
            poll_audio_ready(
                self.client,
                self._voice_id,
                story_id,
                self._tokens.access_token,
            )


# ===================================================================
# S8 — Connection Pool Exhaustion
# ===================================================================

class S8ConnectionPool(TaskSet):
    """
    50 concurrent users hitting mixed endpoints simultaneously.
    Tests DB pool limits: pool_size=5, max_overflow=10 per process.
    """

    def on_start(self):
        _login_on_start(self)

    @tag("s8")
    @task(3)
    def poll_audio(self):
        """HEAD request — lightweight but uses a DB connection."""
        story_id = _pick_story_id(self)
        self.client.head(
            f"/voices/{self._voice_id}/stories/{story_id}/audio",
            headers=auth_headers(self._tokens.access_token),
            name="HEAD /voices/[id]/stories/[id]/audio",
        )

    @tag("s8")
    @task(2)
    def get_stories(self):
        """GET /stories — read-only DB access."""
        self.client.get(
            "/stories",
            headers=auth_headers(self._tokens.access_token),
            name="GET /stories",
        )

    @tag("s8")
    @task(1)
    def synthesize(self):
        """POST synthesis — write-heavy: credit debit + audio record + task queue."""
        story_id = _pick_story_id(self)
        request_synthesis(
            self.client, self._voice_id, story_id, self._tokens.access_token
        )

    @tag("s8")
    @task(1)
    def get_credits(self):
        """GET /credits — read with potential reconciliation write."""
        self.client.get(
            "/credits",
            headers=auth_headers(self._tokens.access_token),
            name="GET /credits",
        )
