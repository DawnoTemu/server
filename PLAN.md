# Task & Context
Design and ship “Elastic Voice Slots for ElevenLabs”: keep user voice recordings in-house, allocate ElevenLabs voices just-in-time during story generation, and recycle limited voice slots fairly so we never exceed the remote cap while preserving a smooth user experience.

## Current State (codebase scan)
- Voice capture & cloning: `routes/voice_routes.py` → `VoiceController.clone_voice` which immediately queues `VoiceModel.clone_voice` to create an ElevenLabs voice; recordings are pushed to S3 temp keys and converted to READY voices in `tasks/voice_tasks.py`.
- Voice data model: `models/voice_model.py` (table `voices`) stores `elevenlabs_voice_id`, sample S3 key, `status` (PENDING/PROCESSING/READY/ERROR); no notion of “recording only” or slot allocation metadata.
- Story synthesis: `routes/audio_routes.py` + `controllers/audio_controller.AudioController.synthesize_audio` require an existing `elevenlabs_voice_id`; Celery worker `tasks/audio_tasks.py` assumes the voice is READY and calls `AudioModel.synthesize_speech`.
- Voice services: `utils/voice_service.py` routes between ElevenLabs/Cartesia with current clone/delete/synthesize helpers; `utils/elevenlabs_service.py` provides direct API calls but has no slot bookkeeping.
- Credits & prioritisation inputs: `models/credit_model.py` maintains per-user balances and last transactions; `models/user_model.py` stores `credits_balance`; no linkage yet to voice eviction decisions.
- Background processing: Celery app exists (see `tasks/__init__.py`), but there is no queue dedicated to slot arbitration or eviction.
- Tests / docs: coverage lives under `tests/test_models/test_voice_model.py`, `tests/test_routes/test_voice_routes.py`, `tests/test_routes/test_audio_routes.py`; docs under `docs/` have no guidance on slot limits or user messaging.

## Proposed Changes (files & functions)
- **Schema & models**
  - Extend `voices` table: add fields such as `recording_s3_key`, `recording_filesize`, `elevenlabs_allocated_at`, `last_used_at`, `slot_lock_expires_at`, `allocation_status` (Recorded|Allocating|Ready|Cooling|Evicted), and `service_provider`. Consider nullable `elevenlabs_voice_id` with unique index only when populated.
  - Optional new table `voice_slot_events` (audit trail of allocations/evictions) if we need historical data for debugging and fairness scoring.
  - Update SQLAlchemy model (`models/voice_model.Voice`) with new columns + helper methods (`mark_recorded`, `mark_allocation_started`, `mark_ready`, `mark_evicted`).
- **Recording flow**
  - Rework `VoiceController.clone_voice` to store the uploaded audio (encrypted S3 object) and create/update a `Voice` row in “Recorded” state without contacting ElevenLabs; return metadata & status.
  - Update `VoiceModel.clone_voice` (and tests) to align with the new behaviour, ensuring we keep storing the original sample for later.
  - Adjust `tasks/voice_tasks.clone_voice_task` or replace it with a new `process_voice_recording` task that just handles post-processing (noise removal, encryption) but does not allocate ElevenLabs.
- **Slot allocation service**
  - Introduce `utils/voice_slot_manager.py` encapsulating:
    - `ensure_active_voice(user_id, voice_id=None)` that acquires a distributed lock, checks if an active ElevenLabs voice exists, and if not triggers allocation workflow.
    - Slot accounting against configured limit (`Config.ELEVENLABS_SLOT_LIMIT`), cached list of active voices, and eviction policy using user activity (`credits_balance`, recent `AudioStory` usage, `last_used_at`, `slot_lock_expires_at`).
    - `select_voice_for_eviction()` implementing fairness rules (inactive, zero credits, oldest last-used, outside warm hold window).
    - API integrations (`create_remote_voice`, `delete_remote_voice`) invoking `utils/elevenlabs_service` and handling drift (missing remote voice).
- **Audio generation changes**
  - Update `AudioController.synthesize_audio` (and corresponding route) to accept an internal voice id or user default, call `VoiceSlotManager.ensure_active_voice` before debiting credits, and receive either the ready remote voice id or a queued/allocating status.
  - Enhance response contract to surface states like `allocating_voice`, `queued_for_slot`, `processing`, aligning with UX messaging expectations.
  - Modify `tasks/audio_tasks.synthesize_audio_task` to wait/retry until allocation finalises (respecting Celery retry/backoff) and to refresh `Voice` metadata (`last_used_at`).
- **Asynchronous orchestration**
  - Add Celery tasks for `allocate_voice_slot` and `evict_voice_slot`; ensure they serialise operations via Redis locks to avoid over-allocation.
  - Implement a lightweight queue/backoff when slots are full using Redis-backed data structures and status flags on the `AudioStory` row (e.g., `allocation_pending`).
  - Provide scheduled cleanup task (`tasks/voice_tasks.reclaim_idle_voices`) to periodically evict voices past cooling window or with missing recordings.
- **API & UX adjustments**
  - Possibly add endpoint `GET /voices/<id>/status` to poll allocation state, or extend existing responses.
  - Update docs (`docs/openapi.yaml`, README voice section) to describe new states and policies.
  - Add admin tools (optional) to inspect current slot usage via `admin.py` or dedicated route.
- **Configuration & secrets**
  - Extend `Config` with `ELEVENLABS_SLOT_LIMIT`, `VOICE_WARM_HOLD_SECONDS`, `VOICE_ALLOCATION_RETRY_LIMIT`, encryption toggles for S3 uploads.
- **Testing**
  - New unit tests for `VoiceSlotManager` (allocation, eviction decision matrix) using pytest-mock.
  - Update route/controller tests to cover allocating responses, queued states, and eviction-trigger scenarios.
  - Add Celery task tests for allocation pipeline (can be mocked).

## Step-by-Step Plan
1. **Define data model extensions**: draft Alembic migration for new columns/table, update `models/voice_model.Voice` and ensure relationships/indexes support nullable remote IDs; add helper enums/consts for allocation statuses.
2. **Refactor recording endpoint**: rewrite `VoiceController.clone_voice`/`VoiceModel.clone_voice` to save encrypted recordings without invoking ElevenLabs; adjust tests & documentation.
3. **Implement VoiceSlotManager**: create utility module handling slot limit config, selection heuristics, eviction routines, and remote API wrappers with comprehensive logging/error handling.
4. **Wire allocation into audio flow**: modify `AudioController.synthesize_audio` and Celery `synthesize_audio_task` to call the manager, manage status transitions, and handle queued/allocating responses while preserving credit charging behaviour.
5. **Add eviction & cleanup tasks**: create Celery tasks for allocation queue processing and periodic reclamation; ensure they update `Voice` records and notify waiting audio jobs.
6. **Update routes & serialization**: adapt `routes/audio_routes.py` (and possibly `voice_routes.py`) to accept internal IDs, expose new statuses, and maintain backward compatibility where required; update OpenAPI spec and user-facing docs.
7. **Testing & validation**: expand pytest coverage (unit + functional) for the new manager, controller changes, and task flows; add fixtures/mocks for ElevenLabs responses.
8. **Operational polish**: document configuration/env expectations, add admin visibility if needed, verify logging/metrics, and run sanity tests (end-to-end voice recording → story generation with slot recycling).

## Risks & Assumptions
- **Concurrency & locking**: multiple generate requests may race for the same slot; we must rely on DB row locks or Redis distributed locks to avoid over-allocation.
- **Remote API limits & latency**: ElevenLabs allocation/deletion calls may be slow or fail; plan requires robust retries and consistent state reconciliation.
- **Eviction policy accuracy**: fairness rules depend on accurate `last_used_at`, credit balance, and warm-hold windows—assumes existing credit ledger is up to date and accessible during allocation.
- **Backwards compatibility**: existing clients may still send `elevenlabs_voice_id`; we need translation or dual support during transition.
- **S3 storage & encryption**: assumes current `S3Client` can apply server-side encryption; may require additional parameters/enforcement.
- **Queue complexity**: introducing allocation queues could stall audio synthesis if not carefully instrumented; need visibility/logging to troubleshoot.

## Validation & Done Criteria
- Recording endpoint stores samples without creating ElevenLabs voices; database shows `allocation_status=recorded`.
- Audio synthesis request triggers allocation when needed, respecting slot limit and returning appropriate state transitions; once a slot frees, queued request completes successfully.
- Eviction logic removes low-priority voices and reuses slots without exceeding configured cap (validated via logs/tests).
- Tests covering allocation manager, eviction heuristics, and updated routes/controllers pass (`pytest -v`).
- Documentation (OpenAPI + README) reflects new workflow and user-visible statuses.
- Observed telemetry/logs confirm slot operations are serialized and recover from failures (e.g., remote voice missing is re-created).

## Open Questions
- Should we introduce a dedicated queue table to persist waiting requests, or is in-memory/Celery retry sufficient?
in-memory/Celery is good
- What is the exact ElevenLabs slot cap (configurable per env) and desired warm-hold duration?
ElevenLabs slot cap can be hanging (we must both set it on ENV current 30 but be reade if eleven labs return Error of non slots available)
 desired warm-hold duratio set something logical 15 minutes?
- Do we need administrative overrides to pin certain voices so they are never evicted?
no
- How should we communicate allocation delays to clients—polling endpoint, WebSocket, or relying on existing job status polling?
Relying on existing job status polling
- Are there compliance requirements for encrypting stored voice recordings beyond S3 server-side encryption (e.g., client-side)?
something trusted aligned with EU GDPR
