"""
Main Locust entry point for DawnoTemu load tests.

Usage:
  # Run all scenarios (mixed traffic)
  locust -f tests/load/locustfile.py --host http://localhost:8000

  # Run a specific scenario via tags
  locust -f tests/load/locustfile.py --host http://localhost:8000 --tags s1

  # Headless mode (CI)
  locust -f tests/load/locustfile.py --host http://localhost:8000 \
    -u 10 -r 2 --run-time 5m --headless --csv results/s1

Available tags: s1, s2, s3, s4, s5, s6, s7, s8
"""

import os
import sys

from locust import HttpUser, between, events, tag

# Ensure the project root is on the path so we can import our modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from tests.load.scenarios import (
    S1ParallelGeneration,
    S2PollingStorm,
    S3QueueSaturation,
    S4ElevenLabsConcurrency,
    S5CreditRace,
    S6SlotQueue,
    S7TokenRefresh,
    S8ConnectionPool,
)


# ---------------------------------------------------------------------------
# User counter for assigning unique test user emails
# ---------------------------------------------------------------------------

@events.init.add_listener
def on_init(environment, **kwargs):
    """Initialize shared state on the Locust environment."""
    environment._user_counter = 0


# ---------------------------------------------------------------------------
# User classes — one per scenario for isolated runs, plus a mixed-traffic user
# ---------------------------------------------------------------------------


class ParallelGenerationUser(HttpUser):
    """S1 — Parallel Generation: POST + poll until COMPLETE."""
    tasks = [S1ParallelGeneration]
    wait_time = between(1, 3)
    weight = 3


class PollingStormUser(HttpUser):
    """S2 — Polling Storm: aggressive HEAD polling."""
    tasks = [S2PollingStorm]
    wait_time = between(0.5, 1)
    weight = 2


class QueueSaturationUser(HttpUser):
    """S3 — Queue Saturation: burst of POST requests."""
    tasks = [S3QueueSaturation]
    wait_time = between(0.1, 0.5)
    weight = 1


class ConcurrencyLimitUser(HttpUser):
    """S4 — ElevenLabs Concurrency: 10 concurrent synthesis tasks."""
    tasks = [S4ElevenLabsConcurrency]
    wait_time = between(1, 3)
    weight = 2


class CreditRaceUser(HttpUser):
    """S5 — Credit Race: double-fire with 1 credit."""
    tasks = [S5CreditRace]
    wait_time = between(0.1, 0.5)
    weight = 1


class SlotQueueUser(HttpUser):
    """S6 — Voice Slot Queue: many distinct voices."""
    tasks = [S6SlotQueue]
    wait_time = between(1, 5)
    weight = 1


class TokenRefreshUser(HttpUser):
    """S7 — Token Refresh Under Load."""
    tasks = [S7TokenRefresh]
    wait_time = between(0.5, 2)
    weight = 1


class ConnectionPoolUser(HttpUser):
    """S8 — Connection Pool Exhaustion: mixed heavy traffic."""
    tasks = [S8ConnectionPool]
    wait_time = between(0.5, 1.5)
    weight = 2
