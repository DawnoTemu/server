# TASK-021: Voice Slot Manager Core

Epic Reference: docs/roadmap/epics/EPIC-002-elastic-elevenlabs-voice-slots.md (EPIC-002)

## Description
Implement a reusable `VoiceSlotManager` utility that encapsulates slot accounting, locking, and remote voice lifecycle (create/delete) so controllers and tasks can request active voices without duplicating logic.

## Plan
- Create `utils/voice_slot_manager.py` with public methods like `ensure_active_voice(user_id, voice_id=None, request_id=None)`, `select_voice_for_eviction()`, and remote API helpers.
- Integrate Redis (or configured lock backend) to guard slot allocation and eviction with distributed locks.
- Incorporate policy rules: cap at `ELEVENLABS_SLOT_LIMIT` (default 30), warm-hold window (`VOICE_WARM_HOLD_SECONDS=900`), preference for users with credits/recent usage.
- Emit structured events to `voice_slot_events` for allocations, evictions, and drift recovery.
- Add unit tests covering slot reuse, eviction selection heuristics, and failure modes (remote create/delete errors).

## Definition of Done
- `VoiceSlotManager` can consistently return a READY voice ID or queue request when slots are exhausted.
- Eviction decisions follow the documented priority (inactive, no credits, stale usage) and never target voices currently synthesising audio.
- Remote voice creation/deletion handles API failures with retries and drift detection.
- Tests validate locking behaviour and core decision logic.*** End Patch
