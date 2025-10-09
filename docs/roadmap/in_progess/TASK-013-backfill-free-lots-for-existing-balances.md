# TASK-013: Backfill Free Lots for Existing Balances

Epic Reference: docs/roadmap/epics/EPIC-001-story-points-credits-system.md (EPIC-001)

## Description
Migrate any pre-existing balances (e.g., `INITIAL_CREDITS`) into non-expiring `free` credit lots so future allocation and expiration logic works consistently. Ensure idempotent backfill.

## Plan
- For each user:
  - If `credits_balance > 0` and no corresponding `free` lot exists, create a `credit_lots` record with `source=free`, `amount_granted=credits_balance`, `amount_remaining=credits_balance`, `expires_at=NULL`.
  - Optionally write an informational `credit_transactions` grant record with reason `backfill_free_lot`.
- Make the script re-runnable without duplicating lots (e.g., detect existing lot or mark via metadata).

## Definition of Done
- All users with positive balances have at least one `free` lot reflecting that amount.
- Idempotent: running multiple times does not inflate balances or lots.
- Tests validate mapping and idempotency.

## Notes
- Coordinate with TASK-010 if both are used; prefer a single cohesive backfill to avoid double-counting.
