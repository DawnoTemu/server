# TASK-006: Refund on Synthesis Failure and Idempotency

Epic Reference: docs/roadmap/epics/EPIC-001-story-points-credits-system.md (EPIC-001)

## Description
Ensure Story Points are refunded automatically when synthesis fails due to technical issues. Make refunds idempotent to tolerate retries and duplicate failure signals, and restore points to the original `credit_lots` used for the debit.

## Plan
- In `tasks/audio_tasks.py` failure paths (including `on_failure`):
  - Call `CreditModel.refund_by_audio(audio_story_id, reason="synthesis_failed")`, which uses `credit_transaction_allocations` to return to the same lots.
  - Log refund outcomes and avoid double-refunds.
- Add tests simulating task exceptions and verifying the ledger contains a debit followed by a matching refund and user balance restoration.

## Definition of Done
- Failed syntheses trigger exactly one refund even with multiple failure signals.
- Balance is restored to the pre-charge amount on failure.
- Tests prove idempotent behavior.
