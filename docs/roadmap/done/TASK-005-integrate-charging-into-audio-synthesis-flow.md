# TASK-005: Integrate Charging into Audio Synthesis Flow

Epic Reference: docs/roadmap/epics/EPIC-001-story-points-credits-system.md (EPIC-001)

## Description
Charge Story Points when queueing new audio synthesis. Do not double-charge for already READY or PROCESSING records. Store `credits_charged` on the `audio_stories` record and allocate debits across `credit_lots` via the CreditModel.

## Plan
- In `AudioController.synthesize_audio`:
  - Retrieve story text; compute required points via `calculate_required_credits`.
  - If existing audio is READY -> return 200 without charge.
  - If existing audio is PROCESSING -> return 202 without charge.
  - For new/failed records: begin transaction; set `AudioStory.status = PENDING` and `credits_charged = required`; call `CreditModel.debit(...)` (lot-aware allocation).
  - On insufficient balance -> rollback and return HTTP 402 with clear message and remaining balance.
  - Queue Celery task as today.
- Add tests: READY/PROCESSING no-charge, new enqueue charges once, insufficient balance path returns 402.

## Definition of Done
- Endpoint `POST /voices/{voice}/stories/{story}/audio` charges exactly once per new synthesis and returns correct status codes.
- `credits_charged` persists on the audio record.
- Tests cover success, repeat calls, and insufficient funds.
