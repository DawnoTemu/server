# Load Testing — DawnoTemu Audio Generation Pipeline

Load tests for verifying the audio generation pipeline can handle real traffic
before launch. Tests cover the full path from HTTP request through Celery queue
to ElevenLabs API and back.

## Prerequisites

- Docker & Docker Compose
- Python 3.13+ (for running tests locally)
- `locust` (`pip install locust`)

## Quick Start (Docker)

```bash
cd server

# Start everything: app + mock ElevenLabs + Locust
docker compose \
  -f docker-compose.yml \
  -f tests/load/docker-compose.loadtest.yml \
  up --build

# Open Locust UI
open http://localhost:8089
```

## Quick Start (Local)

```bash
cd server

# Start app infrastructure
docker compose up -d db redis minio minio-init

# Start mock ElevenLabs in background
MOCK_EL_LATENCY_MIN=1 MOCK_EL_LATENCY_MAX=3 \
  python -m tests.load.mock_elevenlabs_server &

# Start Flask app (pointed at mock)
ELEVENLABS_API_URL=http://localhost:11411 flask run --port 8000 &

# Start Celery worker (pointed at mock)
ELEVENLABS_API_URL=http://localhost:11411 \
  celery -A celery_worker.celery_app worker --loglevel=info &

# Run Locust
locust -f tests/load/locustfile.py --host http://localhost:8000
```

## Scenarios

| Tag | Name | What it tests | Key metrics |
|-----|------|---------------|-------------|
| `s1` | Parallel Generation | N users POST synthesis + poll | p50/p95/p99 completion, error rate |
| `s2` | Polling Storm | Aggressive HEAD polling | HEAD p95 < 300ms, 0% 503 rate |
| `s3` | Queue Saturation | 30 POST burst in 60s | Queue drain time, retry count |
| `s4` | ElevenLabs Concurrency | 10 concurrent synthesis tasks | Concurrency cap enforced, 0 lost jobs |
| `s5` | Credit Race | 1 credit, 2 simultaneous requests | No overdraft, no double-spend |
| `s6` | Voice Slot Queue | 35 voices, 30 slot limit | All eventually complete |
| `s7` | Token Refresh | JWT expiry during load | 0 permanent auth failures |
| `s8` | Connection Pool | 50 users, mixed endpoints | 0 pool exhaustion errors |

### Running a specific scenario

```bash
# Run only S1 (parallel generation)
locust -f tests/load/locustfile.py --host http://localhost:8000 --tags s1

# Run S2 headless for 10 min
locust -f tests/load/locustfile.py --host http://localhost:8000 \
  --tags s2 -u 20 -r 2 --run-time 10m --headless --csv results/s2
```

## Credit Race Test (pytest)

The credit race condition test runs as a standard pytest test against
a real PostgreSQL database, using `ThreadPoolExecutor` to fire concurrent
debit operations:

```bash
cd server
python -m pytest tests/test_credit_race.py -v
```

This test verifies:
- Exactly 1 debit succeeds when user has 1 credit and 10 threads race
- `credits_balance` is never negative
- `SUM(credit_lots.amount_remaining)` matches `credits_balance`
- Debit idempotency works for the same `audio_story_id`

## Mock ElevenLabs Server

The mock server simulates ElevenLabs API behavior:

| Env Var | Default | Description |
|---------|---------|-------------|
| `MOCK_EL_LATENCY_MIN` | `2` | Min synthesis latency (seconds) |
| `MOCK_EL_LATENCY_MAX` | `5` | Max synthesis latency (seconds) |
| `MOCK_EL_ERROR_RATE` | `0.05` | Probability of 500 error |
| `MOCK_EL_RATE_LIMIT_AFTER` | `5` | Max concurrent before 429 |
| `MOCK_EL_PORT` | `11411` | Server port |

Endpoints:
- `POST /v1/text-to-speech/{voice_id}` — Fake MP3 after delay
- `POST /v1/voices/add` — Create mock voice
- `DELETE /v1/voices/{voice_id}` — Delete mock voice
- `GET /health` — Health check
- `GET /metrics` — Internal monitoring

## Configuration

Environment variables for load tests:

| Env Var | Default | Description |
|---------|---------|-------------|
| `LOADTEST_HOST` | `http://localhost:8000` | Target server URL |
| `LOADTEST_USER_COUNT` | `50` | Number of test users |
| `LOADTEST_USER_PASSWORD` | `LoadTest2024!` | Test user password |
| `LOADTEST_USER_EMAIL_TEMPLATE` | `loadtest+{n}@dawnotemu.test` | Email template |
| `LOADTEST_VOICE_ID` | `1` | Default voice ID for tests |
| `LOADTEST_STORY_IDS` | `1,2,3,4,5` | Available story IDs |
| `LOADTEST_ADMIN_API_KEY` | `` | Admin key for user setup |

## Test User Setup

Test users must be pre-created and activated before running load tests.
Use the setup helpers:

```python
from tests.load.helpers import setup_test_users, activate_test_users

# Create 10 test users
setup_test_users(client, count=10)

# Activate them (requires admin API key)
activate_test_users("http://localhost:8000", count=10, admin_key="...")
```

## Acceptance Criteria

From Issue #33:

- **S1 (N=10):** 0% error rate, all COMPLETE, p95 < 5 min
- **S2:** HEAD p95 < 300ms, 0% 503 rate over 10 min
- **S3:** Queue drains within 15 min, 0 ERROR from retry cascade
- **S4:** 0 lost jobs, concurrency enforced
- **S5:** No double-spend, no overdraft
- **S6:** All 35 eventually COMPLETE
- **S7:** 0 permanent auth failures
- **S8:** 0 pool exhaustion errors

## Scaling Locust Workers

```bash
docker compose \
  -f docker-compose.yml \
  -f tests/load/docker-compose.loadtest.yml \
  up --build --scale locust-worker=4
```

## Monitoring During Tests

- **Locust UI:** http://localhost:8089
- **Flower (Celery):** http://localhost:5555 (add `--profile monitoring` to docker compose)
- **Mock ElevenLabs metrics:** http://localhost:11411/metrics
- **Redis queue depth:** `redis-cli LLEN celery`
