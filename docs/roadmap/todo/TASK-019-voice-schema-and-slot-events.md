# TASK-019: Voice Schema & Slot Event Foundations

Epic Reference: docs/roadmap/epics/EPIC-002-elastic-elevenlabs-voice-slots.md (EPIC-002)

## Description
Extend the persistence layer so voices can stay in a recorded state, track slot allocation metadata, and capture queue/eviction activity for future analytics. This includes new columns on `voices` and an events log to observe slot recycling.

## Plan
- Draft Alembic migrations adding voice metadata (`recording_s3_key`, `recording_filesize`, `allocation_status`, `service_provider`, `elevenlabs_allocated_at`, `last_used_at`, `slot_lock_expires_at`) and enforcing uniqueness on populated `elevenlabs_voice_id`.
- Create `voice_slot_events` table with event type, reason, and metadata JSON to audit allocations/evictions.
- Update `models/voice_model.py` and related SQLAlchemy models to expose the new fields and helper enums/constants.
- Ensure migrations run cleanly against Postgres and sqlite (dev) with proper defaults and indexes.

## Definition of Done
- Alembic migrations apply successfully and roll back cleanly.
- `voices` records can exist without an ElevenLabs ID while capturing recording metadata and status transitions.
- New table (`voice_slot_events`) is represented via SQLAlchemy models and accessible in the ORM.
- Tests or simple scripts confirm schema changes are reflected in the database inspector.*** End Patch
