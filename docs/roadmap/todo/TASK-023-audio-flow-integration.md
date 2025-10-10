# TASK-023: Audio Flow Integration

Epic Reference: docs/roadmap/epics/EPIC-002-elastic-elevenlabs-voice-slots.md (EPIC-002)

## Description
Wire the allocation pipeline into story synthesis so audio generation requests coordinate with the new queue/manager, emit user-facing statuses, and refresh voice usage metadata.

## Plan
- Update `AudioController.synthesize_audio` to call `VoiceSlotManager.ensure_active_voice`, handle queued/allocating status responses, and populate enriched payloads (`allocating_voice`, `queued_for_slot`, `processing`, `ready`).
- Adjust Celery `synthesize_audio_task` to wait for allocation completion, refresh `Voice.last_used_at`, and record slot events upon completion.
- Ensure credit charging logic remains idempotent when requests are queued or retried.
- Update routes/tests to accept internal voice IDs and handle new status codes (e.g., 202 with `allocating_voice`).
- Record `voice_slot_events` for significant transitions (queue entry, allocation started, allocation completed).

## Definition of Done
- Generating audio without a ready remote voice yields `allocating_voice`/`queued_for_slot` responses until a slot is available.
- Successful synthesis updates `Voice.last_used_at` and leaves the voice in `Ready`/`Cooling` state per policy.
- Credits are charged only once per audio job, even if queueing introduces delays.
- Tests cover the new controller/task behaviour and response contracts.*** End Patch
