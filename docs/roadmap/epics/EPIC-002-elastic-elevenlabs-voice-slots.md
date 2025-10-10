# Task & Context
Elastic Voice Slots for ElevenLabs: decouple voice recording from remote voice allocation so user recordings stay in-house, ElevenLabs voices are created just-in-time during story generation, and limited remote slots are recycled fairly without breaking the storytelling experience.

## Current State (codebase scan)
- Recording & cloning: `routes/voice_routes.py` → `VoiceController.clone_voice` immediately queues `VoiceModel.clone_voice`, which uploads samples to S3 and triggers `tasks/voice_tasks.clone_voice_task` to call ElevenLabs. Every recording attempts to allocate a remote voice up front.
- Voice model: `models/voice_model.Voice` tracks `elevenlabs_voice_id`, sample key, and status (PENDING/PROCESSING/READY/ERROR) but lacks metadata for “recording-only” states, slot ownership, or allocation timestamps.
- Story synthesis: `routes/audio_routes.py` / `AudioController.synthesize_audio` expect a READY voice with an ElevenLabs ID. Celery `tasks/audio_tasks.synthesize_audio_task` calls `AudioModel.synthesize_speech` assuming the remote voice already exists.
- Integrations: `utils/voice_service.py` and `utils/elevenlabs_service.py` provide clone/delete helpers but no slot accounting or eviction logic.
- Prioritisation signals: credit balances/live usage exist via `models/credit_model.py` and `AudioStory` timestamps, yet they are not leveraged for selecting which voices to keep or evict.
- No orchestration for slot limits: there is no queue, allocation manager, or periodic cleanup; documentation and tests do not mention slot constraints.

## Proposed Changes (files & functions)
- **Schema & models**
  - Extend `voices` table with `recording_s3_key`, `recording_filesize`, `allocation_status` (Recorded|Allocating|Ready|Cooling|Evicted), `service_provider`, `elevenlabs_allocated_at`, `last_used_at`, and `slot_lock_expires_at`. Keep `elevenlabs_voice_id` nullable with a uniqueness constraint when populated.
  - Add `voice_slot_events` (id, voice_id, user_id, event_type, reason, metadata JSON, created_at) for observability of allocations, evictions, and queue transitions.
  - Update `models/voice_model.Voice` to surface helper methods for state transitions and to encapsulate S3 sample metadata.
- **Recording flow**
  - Refactor `VoiceController.clone_voice` / `VoiceModel.clone_voice` so uploads store encrypted recordings (server-side AES256 by default) and leave voices in “Recorded” state without touching ElevenLabs.
  - Replace `tasks/voice_tasks.clone_voice_task` with a lightweight `process_voice_recording` task that handles audio hygiene (noise removal, format validation) and populates recording metadata only.
- **Voice slot manager**
  - Create `utils/voice_slot_manager.py` implementing `ensure_active_voice(user_id, voice_id=None, request_id=None)` that acquires a Redis/distributed lock, checks slot availability, reuses existing READY voices, or orchestrates allocation.
  - Maintain slot accounting against `Config.ELEVENLABS_SLOT_LIMIT` (default 30) and apply eviction policy using `credits_balance`, `last_used_at`, warm-hold window, and eligibility flags.
  - Provide helpers `create_remote_voice(voice)` and `delete_remote_voice(voice)` with resilient error handling and drift recovery when ElevenLabs voices go missing.
- **Queueing & eviction**
  - Maintain a Redis-backed queue (list or sorted set) that tracks waiting allocation requests without introducing new relational tables.
  - Add Celery tasks: `allocate_voice_slot_task`, `process_voice_queue_task`, and `reclaim_idle_voices_task` to serialise allocations, handle backlog, and recycle stale voices after the warm-hold window (15 minutes by default).
  - Implement `select_voice_for_eviction()` to choose candidates with zero credits, long inactivity, or stale cooling status while never interrupting active synthesis.
- **Audio generation updates**
  - Update `AudioController.synthesize_audio` to invoke `VoiceSlotManager.ensure_active_voice` before debiting credits. Return enriched payloads (`status: allocating_voice | queued_for_slot | processing | ready`) so the frontend can mirror queue/allocate/generate states.
  - Adjust `tasks/audio_tasks.synthesize_audio_task` to poll/wait for allocation completion, refresh `Voice.last_used_at`, and record slot events.
- **API, admin, and docs**
  - Extend `routes/audio_routes.py` and `routes/voice_routes.py` to support polling voice status and exposing queue position when relevant.
  - Add admin views (Flask-Admin / blueprint endpoints) summarising active slots, queued requests, and eviction history for operational clarity.
  - Update `docs/openapi.yaml`, README voice section, and create `docs/ElasticVoiceSlots.md` summarising workflow, queue states, and fairness rules.
- **Configuration**
  - Add `ELEVENLABS_SLOT_LIMIT`, `VOICE_WARM_HOLD_SECONDS` (900s default), `VOICE_ALLOCATION_RETRY_LIMIT`, and `VOICE_RECORDING_ENCRYPTION` toggles in `Config`.
  - Ensure S3 uploads enforce encryption (SSE-S3 by default, optional KMS key via env).
- **Testing**
  - Unit tests for VoiceSlotManager (allocation, eviction heuristics, queue ordering) with pytest-mock.
  - Functional tests covering recording-only flow, queued allocation, successful eviction, and drift recovery in routes/controllers.
  - Celery task tests verifying retries/backoff and queue progression.

## Step-by-Step Plan
1. **Data model foundation**: Ship Alembic migrations for voice metadata and slot events; update SQLAlchemy models and enums.
2. **Recording refactor**: Rework recording endpoints/tasks to store encrypted samples without remote allocation; adjust S3 interactions and unit tests.
3. **Slot manager & locking**: Implement `VoiceSlotManager` with Redis locks, slot accounting, allocation, eviction heuristics, and remote API wrappers.
4. **Queue processing**: Implement Redis-backed queue handling plus Celery tasks (`allocate_voice_slot_task`, `process_voice_queue_task`, `reclaim_idle_voices_task`) and eviction/cleanup workflows.
5. **Audio flow integration**: Update `AudioController`/Celery tasks to call the manager, surface new statuses, and refresh voice usage metadata.
6. **Admin & observability**: Build admin-facing views/routes and emit structured logs/events for allocations, evictions, and queue transitions.
7. **Documentation & UX**: Refresh OpenAPI spec, README, and add user-facing docs describing queued/allocating messaging and privacy posture.
8. **Testing & rollout**: Expand pytest coverage (unit + functional), run smoke tests for slot recycling, and prepare rollout checklist (feature flag, monitoring).

## Risks & Assumptions
- Concurrency: allocation and eviction require strict locking to prevent exceeding slot limits; assumes Redis is available for distributed locks.
- Remote API latency: ElevenLabs create/delete calls may be slow; plan relies on retries and drift recovery to keep state consistent.
- Eviction fairness: heuristics depend on accurate credit balances and `last_used_at`; assumes existing credit ledger remains authoritative.
- Backward compatibility: existing clients passing `elevenlabs_voice_id` need translation or deprecation messaging during migration.
- Queue visibility: improper instrumentation could hide stuck requests; plan assumes logging/metrics will be added alongside queue processing.
- S3 encryption: relies on AWS SSE-S3 or configured KMS key to satisfy “recordings stored encrypted” requirement.

## Validation & Done Criteria
- Recording endpoint stores samples with `allocation_status=recorded`, no ElevenLabs voice created until generation time.
- Generating a story with “my voice” triggers `allocating_voice` or `queued_for_slot` states when slots are constrained and eventually proceeds once a slot frees.
- Slot usage never exceeds `ELEVENLABS_SLOT_LIMIT`; eviction logs confirm low-priority voices are recycled while active jobs remain uninterrupted.
- Redis-backed queue ensures >30 concurrent requests are processed without errors; warm-hold window (15 minutes) is honoured before eviction.
- Admin/operational tooling shows current slot utilisation, queue depth, and recent evictions.
- pytest suite covers allocation manager, queueing, and controller/task changes (`pytest -v` passes).
- Documentation updates explain new workflow and privacy posture.

## Resolved Decisions from Prior Open Questions
- **Queue persistence**: Use Redis/Celery coordination (no new relational tables) to manage waiting requests while enforcing slot caps.
- **Slot cap & warm hold**: Default `ELEVENLABS_SLOT_LIMIT=30`; warm-hold window set to 15 minutes (`VOICE_WARM_HOLD_SECONDS=900`) before voices become eviction candidates.
- **Administrative pinning**: MVP excludes pin/protect features; monitor utilisation first and add overrides later if necessary.
- **Client communication**: Continue using HTTP polling with enriched status payloads; no WebSocket investment for this release.
- **Recording encryption**: Enforce S3 server-side encryption (AES256) by default, with optional KMS configuration for stricter environments.
