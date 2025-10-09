# TASK-002: Database Schema for Credits Ledger and Balances

Epic Reference: docs/roadmap/epics/EPIC-001-story-points-credits-system.md (EPIC-001)

## Description
Extend the database to support Story Points accounting with future-proof expirations. Add a running balance on users, record credits charged per audio job, a `credit_transactions` ledger, and per-source `credit_lots` with allocation mappings.

## Plan
- Alembic migration:
  - Add `users.credits_balance INTEGER NOT NULL DEFAULT 0` (cache; may be recomputed).
  - Add `audio_stories.credits_charged INTEGER NULL`.
  - Create `credit_transactions` with: `id`, `user_id` (FK users), `amount` (INTEGER, signed), `type` (VARCHAR), `reason` (VARCHAR), `audio_story_id` (FK audio_stories, nullable), `story_id` (FK stories, nullable), `status` (VARCHAR), `metadata` (JSON, nullable), `created_at`, `updated_at`.
  - Add unique index to prevent duplicate debit per `audio_story_id` (and `type='debit'` via partial index if supported).
  - Create `credit_lots` with: `id`, `user_id` (FK users), `source` (VARCHAR or ENUM: monthly|add_on|free|event|referral), `amount_granted` (INTEGER), `amount_remaining` (INTEGER), `expires_at` (TIMESTAMP NULL), `created_at`, `updated_at`; index on (`user_id`, `expires_at`).
  - Referral lots: by default set `expires_at = NULL` (non-expiring); can be configured later if policy changes.
  - Create `credit_transaction_allocations` with: `transaction_id` (FK credit_transactions), `lot_id` (FK credit_lots), `amount` (INTEGER, signed); composite PK (`transaction_id`,`lot_id`).
- Generate `upgrade()`/`downgrade()` and test on local DB.

## Definition of Done
- Migration applies and rolls back cleanly.
- New columns/tables visible via SQLAlchemy metadata.
- Constraints and indexes created as specified.
- Basic smoke tests confirm default `credits_balance=0`, nullable `credits_charged`, and lot/allocations integrity.

## Notes
- Consider a data backfill for existing users (handled in TASK-010).
