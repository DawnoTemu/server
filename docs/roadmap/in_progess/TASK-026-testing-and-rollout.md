# TASK-026: Testing & Rollout Readiness

Epic Reference: docs/roadmap/epics/EPIC-002-elastic-elevenlabs-voice-slots.md (EPIC-002)

## Description
Validate the end-to-end flow with automated tests and prepare operational safeguards before enabling elastic voice slots in production.

## Plan
- Expand pytest coverage across unit (VoiceSlotManager, queue models), integration (controller + Celery interactions), and regression scenarios (eviction drift, retry loops).
- Add fixtures/mocks for ElevenLabs API to simulate slot exhaustion, API failures, and remote voice deletion.
- Run smoke tests that record a voice, queue >30 generate requests, and confirm queued jobs complete after eviction.
- Prepare rollout checklist: feature flag strategy, monitoring dashboards, alert thresholds, and rollback steps.
- Coordinate with ops to ensure Redis/config values (`ELEVENLABS_SLOT_LIMIT`, warm-hold) are set for each environment.

## Definition of Done
- `pytest -v` passes with new coverage and protects key allocation/eviction paths.
- Smoke test or staging run demonstrates slot recycling without exceeding cap.
- Rollout checklist and monitoring plan are documented and signed off.
- Configuration for all environments is prepared (or gated behind a feature flag) before launch.*** End Patch
