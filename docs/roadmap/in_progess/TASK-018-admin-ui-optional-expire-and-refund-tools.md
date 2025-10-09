# TASK-018: Admin UI — Optional Expire Lot and Refund Tools

Epic Reference: docs/roadmap/epics/EPIC-001-story-points-credits-system.md (EPIC-001)

## Description
For advanced support, add guarded tools to expire a specific lot early and to issue a targeted refund by audio_story_id if needed. These should be clearly labeled and require confirmation.

## Plan
- Add two admin-only endpoints or actions:
  - Expire lot: set `amount_remaining=0` on a selected `CreditLot` and adjust cached balance.
  - Refund by audio: call `refund_by_audio(audio_story_id, reason)`.
- UI: simple forms in admin with confirmation dialogs; log all actions.
- Restrict access (admin_required) and validate inputs robustly.

## Definition of Done
- Admin can expire a selected lot and see the balance reflect the change.
- Admin can issue a targeted refund; ledger records are created and idempotent behavior is preserved.
- All actions require confirmation and display success/error flash messages.

