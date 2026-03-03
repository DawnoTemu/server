"""
Load test configuration and acceptance thresholds.

Thresholds are derived from Issue #33 acceptance criteria and
refined based on architecture analysis of the audio generation pipeline.
"""

import os

# ---------------------------------------------------------------------------
# Target host
# ---------------------------------------------------------------------------
TARGET_HOST = os.getenv("LOADTEST_HOST", "http://localhost:8000")

# ---------------------------------------------------------------------------
# Test user configuration
# ---------------------------------------------------------------------------
TEST_USER_COUNT = int(os.getenv("LOADTEST_USER_COUNT", "50"))
TEST_USER_PASSWORD = os.getenv("LOADTEST_USER_PASSWORD", "LoadTest2024!")
TEST_USER_EMAIL_TEMPLATE = os.getenv(
    "LOADTEST_USER_EMAIL_TEMPLATE",
    "loadtest+{n}@dawnotemu.test",
)

# Pre-shared admin API key (used for setup scripts only, not load test traffic)
ADMIN_API_KEY = os.getenv("LOADTEST_ADMIN_API_KEY", "")

# ---------------------------------------------------------------------------
# Scenario-specific settings
# ---------------------------------------------------------------------------

# S1 - Parallel Generation
S1_CONCURRENT_USERS = [5, 10, 20, 50]
S1_RAMP_RATE = 2  # users/sec

# S2 - Polling Storm
S2_POLL_INTERVAL_SEC = 5
S2_POLL_TIMEOUT_SEC = 600  # 10 min max poll
S2_USER_COUNT = 20

# S3 - Queue Saturation (burst)
S3_BURST_REQUESTS = 30
S3_BURST_WINDOW_SEC = 60
S3_QUEUE_DRAIN_TIMEOUT_SEC = 900  # 15 min

# S4 - ElevenLabs concurrency
S4_CONCURRENT_TASKS = 10

# S5 - Credit race
S5_USERS = 10
S5_CREDITS_PER_USER = 1
S5_CONCURRENT_REQUESTS_PER_USER = 2

# S6 - Voice slot queue
S6_DISTINCT_VOICES = 35
S6_SLOT_LIMIT = 30

# S7 - Token refresh under load
S7_DURATION_SEC = 600  # 10 min

# S8 - Connection pool exhaustion
S8_CONCURRENT_USERS = 50

# ---------------------------------------------------------------------------
# Acceptance thresholds
# ---------------------------------------------------------------------------
THRESHOLDS = {
    # S1 - Parallel Generation
    "s1_error_rate": 0.0,
    "s1_p95_completion_sec": 300,  # 5 min

    # S2 - Polling Storm
    "s2_head_p95_ms": 300,
    "s2_503_rate": 0.0,

    # S3 - Queue Saturation
    "s3_queue_drain_min": 15,
    "s3_error_tasks": 0,

    # S4 - ElevenLabs Concurrency
    "s4_lost_jobs": 0,
    "s4_max_concurrent": 5,

    # S5 - Credit Race
    "s5_overdraft_count": 0,
    "s5_double_spend_count": 0,

    # S6 - Voice Slot Queue
    "s6_all_complete": True,

    # S7 - Token Refresh
    "s7_permanent_auth_failures": 0,
    "s7_refresh_p95_ms": 500,

    # S8 - Connection Pool Exhaustion
    "s8_pool_exhaustion_errors": 0,
}

# ---------------------------------------------------------------------------
# Redis monitoring keys
# ---------------------------------------------------------------------------
REDIS_CELERY_QUEUE_KEY = "celery"
REDIS_SYNTH_CONCURRENCY_KEY = "concurrency:elevenlabs:synth"
REDIS_VOICE_QUEUE_KEY = "voice_slot_queue"
