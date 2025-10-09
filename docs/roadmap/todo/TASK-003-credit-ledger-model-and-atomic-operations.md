# TASK-003: Credit Ledger Model and Atomic Operations

Epic Reference: docs/roadmap/epics/EPIC-001-story-points-credits-system.md (EPIC-001)

## Description
Introduce a ledger with per-source credit lots to mutate balances safely, support expirations, and audit all changes. Provide `debit`, `refund_by_audio`, and `grant` operations with idempotency, row-level locking, and lot allocation.

## Plan
- Add `models/credit_model.py`:
  - `debit(user_id, amount, reason, audio_story_id, story_id) -> (ok, tx)` allocates across `credit_lots` in priority order, records `credit_transaction_allocations`, updates `amount_remaining` and cached `credits_balance`.
  - `refund_by_audio(audio_story_id, reason) -> (ok, tx)` (idempotent), restores amounts to the same lots using recorded allocations.
  - `grant(user_id, amount, reason, source, expires_at=None) -> (ok, lot_or_tx)` creates a lot (or increases `amount_remaining` on a compatible, non-expired lot if we choose to coalesce). Include `source="referral"` for referral bonuses (non-expiring by default).
- Use `SELECT ... FOR UPDATE` on the `User` row and selected `credit_lots` while updating balances.
- Insert a `credit_transactions` row per mutation; set `status` accordingly and allocations.
- Enforce single debit per `audio_story_id` with app-side check + DB constraint (TASK-002).
- Unit tests: concurrent debit attempts; allocation order `event -> monthly -> referral -> add_on -> free`; refund idempotency; partial-lot allocations.

## Definition of Done
- CreditModel implements the three operations with transactions, locking, and lot allocation.
- Comprehensive tests cover normal flow, insufficient balance, idempotent refund, concurrency, and partial-lot allocation.
- Coverage shows all branches executed for success and failure paths.

## Notes
- Insufficient balance should raise a typed error for controller mapping to HTTP 402.
