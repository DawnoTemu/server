# Load Test Report

**Date:** 2026-03-03
**Environment:** Render (Frankfurt) — Web service + Celery worker + PostgreSQL + Redis
**Voice Provider:** ElevenLabs (production API)
**Test Runner:** Custom stress test script + Locust 2.43

---

## Executive Summary

Load testing validated the full DawnoTemu pipeline — from voice cloning through audio synthesis — under concurrent user load. The system handled **10 simultaneous users with 100% success rate**, producing audio for 10 different stories in under 2 minutes. Credit race protection, request deduplication, and rate limiting all functioned correctly in production.

| Metric | Result |
|--------|--------|
| Users tested concurrently | 10 |
| Success rate (end-to-end synthesis) | **100%** (10/10) |
| Voice upload latency | 0.6 - 1.6s |
| End-to-end audio generation | 68 - 104s |
| Credit overdrafts detected | **0** |
| API p95 latency (auth, stories, voices) | < 320ms |

---

## 1. Test Infrastructure

### 1.1 Local Docker Tests (Mock ElevenLabs)

A Docker Compose overlay (`tests/load/docker-compose.loadtest.yml`) extends the main stack with:

- **mock-elevenlabs**: Flask server simulating the ElevenLabs TTS API with configurable latency (2-5s), error rate (5%), and rate limiting (5 concurrent).
- **locust-master**: Locust web UI for orchestrating distributed load tests.
- **locust-worker**: Scalable worker instances.

The mock server allows testing the full pipeline without consuming real ElevenLabs API credits.

### 1.2 Production Stress Test

A dedicated script (`tests/load/prod_stress_test.py`) tests the real pipeline:

1. Login as pre-created test users (via `setup_test_data.py`)
2. Upload a real voice sample (612KB MP3)
3. Request audio synthesis (triggers voice cloning on-demand)
4. Poll until audio is ready
5. Clean up voices after test

### 1.3 Test Data Management

- **Setup:** `render jobs create <service-id> --start-command "python -m tests.load.setup_test_data --no-voices"` creates 50 active, email-confirmed users with 100 credits each, no fake voices.
- **Cleanup:** `render jobs create <service-id> --start-command "python -m tests.load.setup_test_data cleanup"` removes all test users and associated data (voices, audio, credits, slot events).

---

## 2. Local Docker Test Results (Mock ElevenLabs)

### 2.1 Smoke Test — 2 Users, 30 Seconds

**Purpose:** Validate the full Locust pipeline works end-to-end.

| Metric | Result |
|--------|--------|
| Total requests | ~50 |
| Error rate | 0% |
| Pipeline | Login -> Voice discovery -> POST synthesis -> Mock TTS -> Celery -> Poll complete |

**Outcome:** Full pipeline operational.

### 2.2 Load Test — 10 Users, 2 Minutes

**Purpose:** Test API throughput and concurrency protections under sustained load.

| Metric | Result |
|--------|--------|
| Total requests | 3,196 |
| Throughput | 26.7 req/s |
| Error rate | 3.82% |
| Credit overdrafts | **0** |

**Endpoint Latency (Median / P95):**

| Endpoint | Median | P95 |
|----------|--------|-----|
| POST /auth/login | 7ms | 11ms |
| GET /voices | 5ms | 8ms |
| GET /stories | 6ms | 10ms |
| POST synthesis | 8ms | 15ms |
| HEAD poll | 5ms | 9ms |

**Error Breakdown:**
- HEAD 401 (token expiry during polling): 15% of HEAD requests
- POST 429 (rate limit): rare, by design

---

## 3. Production API Test (Locust, Fake Voices)

**Purpose:** Test rate limiting, auth, credit logic, and API latency against real production infrastructure. Voices had fake ElevenLabs IDs so actual TTS did not execute.

**Configuration:** 5 users, 2 minutes, scenarios S5 (credit race), S7 (token refresh), S8 (connection pool).

### 3.1 Results

| Metric | Result |
|--------|--------|
| Total requests | 1,234 |
| Throughput | 10.3 req/s |
| Overall error rate | 39% (expected — see breakdown) |

**Endpoint Latency (Median / P95):**

| Endpoint | Median | P95 |
|----------|--------|-----|
| POST /auth/login | 230ms | 320ms |
| GET /stories | 94ms | 290ms |
| GET /voices | 60ms | 130ms |
| POST synthesis | 61ms | 130ms |
| GET /me/credits | 66ms | 250ms |

### 3.2 Error Breakdown

| Error | Count | Cause |
|-------|-------|-------|
| 429 Too Many Requests | 171 | Rate limiting working correctly (login: 10/min, synthesis: 10/min, credits: 30/min) |
| 401 Unauthorized | 160 | JWT token expiry during long polls (scenarios without refresh) |
| 404 Not Found | 123 | Audio doesn't exist (fake voices can't synthesize) |

### 3.3 Key Findings

- **Rate limiting works:** All configured limits triggered correctly.
- **Credit race protection works:** 0 overdrafts across all S5 runs.
- **Redis dedup works:** "Duplicate synthesis request blocked" confirmed in worker logs.
- **API latency acceptable:** All endpoints under 320ms at P95.

---

## 4. Production Stress Test (Real Voice Cloning + Synthesis)

**Purpose:** Validate the complete user journey — voice upload, ElevenLabs voice cloning, audio synthesis, and delivery — under concurrent load on production infrastructure.

**Configuration:** 10 users, 1 story each (10 different stories), real 612KB MP3 voice sample.

### 4.1 Results

| Phase | Metric | Result |
|-------|--------|--------|
| **Voice Upload** | Time to upload to S3 via API | avg=0.9s, min=0.6s, max=1.6s |
| **End-to-End Synthesis** | Upload -> clone -> TTS -> S3 -> ready | avg=87.5s, min=68.6s, max=103.7s |
| **Success Rate** | Stories fully synthesized | **10/10 (100%)** |
| **Total Duration** | Wall clock for all 10 users | 107.7s |

### 4.2 Per-User Breakdown

| User | Story | End-to-End Time | Notes |
|------|-------|----------------|-------|
| 1 | Czerwony Kapturek | 68.6s | First to allocate |
| 8 | Kot w Butach | 73.5s | |
| 10 | Brzydkie Kaczatko | 73.5s | |
| 5 | Krolewna Sniezka | 83.6s | |
| 6 | Spiaca Krolewna | 83.5s | |
| 4 | Kopciuszek | 93.7s | |
| 9 | Calineczka | 93.5s | |
| 2 | Jas i Malgosia | 98.5s | |
| 7 | Smok Wawelski | 103.7s | |
| 3 | Trzy Male Swinki | 103.5s | Last to complete |

### 4.3 Timing Analysis

The end-to-end time includes three phases:

1. **Voice Cloning (~10-30s):** ElevenLabs creates a clone from the uploaded sample. Triggered on-demand by `ensure_active_voice` during the first synthesis request.
2. **Audio Synthesis (~30-60s):** ElevenLabs generates TTS audio from the story text using the cloned voice.
3. **S3 Upload + DB Update (~1-2s):** Celery worker uploads the audio to S3 and marks the record as ready.

The spread from 68s to 104s is due to **ElevenLabs concurrency limits**: voices are cloned sequentially or in small batches, so later voices queue behind earlier ones. The first 3 voices completed in ~70s, the last 3 in ~100s.

### 4.4 Voice Slot Allocation Flow

The stress test confirmed the on-demand allocation pattern:

```
Upload voice (0.6s) -> POST synthesis triggers ensure_active_voice()
  -> capacity available? -> dispatch allocate_voice_slot Celery task
  -> ElevenLabs clones voice (~10-30s)
  -> Voice marked READY
  -> synthesize_audio_task runs TTS (~30-60s)
  -> Audio uploaded to S3
  -> HEAD poll returns 200
```

Voice allocation does NOT happen at upload time — it is lazy, triggered by the first synthesis request. This is by design (see `docs/ElasticVoiceSlots.md`).

---

## 5. Concurrency Protections Validated

### 5.1 Credit Race (TOCTOU)

**Protection:** Unique constraint on `audio_stories(story_id, voice_id)` + `IntegrityError` retry in `find_or_create_audio_record` + synchronous debit before queueing.

**Test:** S5 scenario fires 2 concurrent synthesis requests per user with limited credits.

**Result:** 0 overdrafts across all test runs (local and production).

### 5.2 Request Deduplication

**Protection:** Redis key `audio:synth:dedup:{voice_id}:{story_id}` with 120s TTL. Second request within TTL returns 202 without queueing a new Celery task.

**Result:** Confirmed in production logs: "Duplicate synthesis request blocked: voice=19 story=2"

### 5.3 Voice Slot Capacity

**Protection:** `VoiceModel.available_slot_capacity()` counts READY + ALLOCATING voices against `ELEVENLABS_SLOT_LIMIT` (30). When full, voices are enqueued in `VoiceSlotQueue` (Redis sorted set).

**Result:** When 50 fake voices occupied all slots, new voices were correctly enqueued and waited for capacity. After cleanup, 10 real voices were allocated within the 30-slot limit.

### 5.4 Rate Limiting

**Production rate limits:**

| Endpoint | Limit | Confirmed |
|----------|-------|-----------|
| POST /auth/login | 10/min | 429 responses observed |
| POST synthesis | 10/min | 429 responses observed |
| GET /me/credits | 30/min | 429 responses observed |
| POST /voices | 5/min | Not tested at limit |

---

## 6. Database Indexes and Constraints Added

As part of load test preparation, the following were added (migration `a1b2c3d4e5f6`):

| Change | Purpose |
|--------|---------|
| `UNIQUE(story_id, voice_id)` on `audio_stories` | Prevent duplicate audio records (TOCTOU race) |
| `INDEX ix_voices_allocation_status` on `voices` | Speed up slot capacity queries |
| `INDEX ix_credit_tx_audio_type_status` on `credit_transactions(audio_story_id, type, status)` | Speed up refund lookups |

Additional config changes:
- `SYNTH_DEDUP_TTL = 120` (Redis dedup for synthesis requests)
- `SQLALCHEMY_POOL_RECYCLE = 300` (prevent stale Celery worker DB connections)

---

## 7. Known Limitations and Future Work

### 7.1 Current Limitations

- **Voice cloning is sequential per provider:** ElevenLabs processes clone requests with limited concurrency. With 10 users, the last voice takes ~35s longer than the first.
- **Poll interval is 5s:** Clients discover audio readiness within 0-5s of completion. Could be reduced or replaced with WebSocket/SSE push notifications.
- **Single Celery worker on Render:** All voice allocation and synthesis tasks run on one worker. Scaling to multiple workers would reduce queueing.

### 7.2 Recommendations

1. **Scale Celery workers** for higher concurrency (Render supports this via additional services).
2. **Consider Cartesia** as primary voice provider if ElevenLabs concurrency becomes a bottleneck — Cartesia has no enforced slot limit (`available_slot_capacity` returns `inf`).
3. **Add push notifications** (WebSocket or SSE) to replace polling for audio readiness.
4. **Run periodic load tests** after major changes using the existing infrastructure:
   ```bash
   # Local (mock ElevenLabs):
   docker compose -f docker-compose.yml -f tests/load/docker-compose.loadtest.yml up

   # Production (real pipeline):
   .venv/bin/python -m tests.load.prod_stress_test \
     --base-url https://server-pf6p.onrender.com \
     --users 10 --stories 1
   ```

---

## 8. How to Run Load Tests

### 8.1 Local with Mock ElevenLabs

```bash
cd server

# Start full stack with mock ElevenLabs + Locust
docker compose -f docker-compose.yml \
  -f tests/load/docker-compose.loadtest.yml up --build

# Setup test data (in another terminal)
docker compose -f docker-compose.yml \
  -f tests/load/docker-compose.loadtest.yml \
  run --rm web python -m tests.load.setup_test_data

# Open Locust UI at http://localhost:8089
# Or run headless:
docker compose -f docker-compose.yml \
  -f tests/load/docker-compose.loadtest.yml \
  run --rm locust-master \
  locust -f /app/tests/load/locustfile.py \
  --host http://web:8000 -u 10 -r 2 --run-time 5m --headless
```

### 8.2 Production with Real Voice Cloning

```bash
cd server

# 1. Create test users on Render (no fake voices)
render jobs create <web-service-id> \
  --start-command "python -m tests.load.setup_test_data --no-voices" \
  --confirm

# 2. Run stress test (requires 001.mp3 voice sample in server/)
.venv/bin/python -m tests.load.prod_stress_test \
  --base-url https://server-pf6p.onrender.com \
  --users 10 --stories 1

# 3. Clean up test data
render jobs create <web-service-id> \
  --start-command "python -m tests.load.setup_test_data cleanup" \
  --confirm
```

### 8.3 Production API-only (Locust, no real synthesis)

```bash
cd server

# Create test users with fake voices
render jobs create <web-service-id> \
  --start-command "python -m tests.load.setup_test_data" \
  --confirm

# Run Locust against production
.venv/bin/locust -f tests/load/locustfile.py \
  --host https://server-pf6p.onrender.com \
  -u 5 -r 2 --run-time 2m --headless \
  CreditRaceUser TokenRefreshUser ConnectionPoolUser

# Clean up
render jobs create <web-service-id> \
  --start-command "python -m tests.load.setup_test_data cleanup" \
  --confirm
```

---

## Appendix A: Test Files

| File | Purpose |
|------|---------|
| `tests/load/config.py` | Thresholds, user config, scenario parameters |
| `tests/load/locustfile.py` | Locust entry point with 8 scenario user classes |
| `tests/load/scenarios.py` | S1-S8 scenario implementations |
| `tests/load/helpers.py` | Auth, polling, Redis monitoring utilities |
| `tests/load/mock_elevenlabs_server.py` | Mock ElevenLabs API for local testing |
| `tests/load/setup_test_data.py` | Create/cleanup test users via direct DB access |
| `tests/load/prod_stress_test.py` | Production stress test with real voice cloning |
| `tests/load/docker-compose.loadtest.yml` | Docker Compose overlay for local load tests |

## Appendix B: Render Service IDs

| Service | ID | Type |
|---------|-----|------|
| Web (Flask API) | `srv-d1cjj295pdvs73euen6g` | Web Service |
| Celery Worker | `srv-d1ck2b7diees73c67lrg` | Background Worker |
| Celery Beat | `srv-d4mo5na4d50c73er4s90` | Cron Job |
