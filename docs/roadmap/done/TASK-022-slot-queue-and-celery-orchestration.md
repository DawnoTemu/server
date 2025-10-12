# TASK-022: Slot Queue & Celery Orchestration

Epic Reference: docs/roadmap/epics/EPIC-002-elastic-elevenlabs-voice-slots.md (EPIC-002)

## Description
Coordinate a Redis-backed queue and Celery workflows that allocate voices, process waiting requests, and reclaim idle slots without exceeding the ElevenLabs cap.

## Plan
- Define Redis data structures (e.g., sorted set for priority, hash for request metadata) to capture queued allocation attempts.
- Add Celery tasks: `allocate_voice_slot_task`, `process_voice_queue_task`, and `reclaim_idle_voices_task`, ensuring they coordinate with `VoiceSlotManager`.
- Ensure tasks acquire locks before allocating/evicting and update request/voice status atomically (status persisted on the `AudioStory`/`Voice` records as needed).
- Handle warm-hold logic (15-minute default) and avoid interrupting active synthesis jobs when reclaiming slots.
- Provide monitoring hooks/logging to debug stuck queue items.

## Definition of Done
- Queue-backed Celery tasks can accept new requests, allocate slots in order, and evict idle voices when needed without relying on new relational tables.
- Redis entries representing waiting jobs transition through expected states, with retries on transient failures.
- Warm-hold window is honoured; eviction never affects voices linked to active audio tasks.
- Logging/metrics make it easy to trace queue depth and recent evictions.*** End Patch
