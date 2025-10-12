# TASK-020: Recording Flow Refactor

Epic Reference: docs/roadmap/epics/EPIC-002-elastic-elevenlabs-voice-slots.md (EPIC-002)

## Description
Rework the voice recording pipeline so that uploading a sample stores an encrypted asset and leaves the voice in a “Recorded” state, deferring ElevenLabs allocation until story generation time.

## Plan
- Update `VoiceController.clone_voice` and `VoiceModel.clone_voice` to save samples to the permanent S3 location, capture metadata, and skip remote voice creation.
- Replace or slim down `tasks/voice_tasks.clone_voice_task` into `process_voice_recording` that handles audio hygiene (noise reduction, format validation) while updating the new metadata fields.
- Ensure S3 uploads enforce server-side encryption (AES256 by default, optional KMS) and store file size/duration where available.
- Adjust API responses and tests so clients receive status `recorded` (or equivalent) with voice IDs ready for later allocation.
- Migrate existing READY voices gracefully, ensuring they retain remote IDs and align with the new status enum.

## Definition of Done
- Recording endpoint returns immediately with a “recorded” voice containing S3 metadata and no ElevenLabs ID.
- Background task (if any) completes non-destructive processing without contacting ElevenLabs.
- Updated unit tests cover the new flow and confirm encryption parameters are passed to S3.
- Existing READY voices continue functioning, and documentation/examples reflect the new recording state.*** End Patch
