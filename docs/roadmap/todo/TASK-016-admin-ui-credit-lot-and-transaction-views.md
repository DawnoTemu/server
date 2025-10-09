# TASK-016: Admin UI — Credit Lots and Transactions Views (Read-Only)

Epic Reference: docs/roadmap/epics/EPIC-001-story-points-credits-system.md (EPIC-001)

## Description
Register read-only views for `CreditLot` and `CreditTransaction` in Flask‑Admin to aid support and auditing.

## Plan
- In `admin.py`:
  - Create `CreditLotModelView` and `CreditTransactionModelView` subclasses of `SecureModelView` with `can_create=False`, `can_edit=False`, `can_delete=False`.
  - Lots columns: id, user_id, source, amount_granted, amount_remaining, expires_at, created_at.
  - Transactions columns: id, user_id, type, amount, status, reason, audio_story_id, story_id, created_at.
  - Add filters by user_id, source, status, created_at/ expires_at.
  - Register both views with Admin.

## Definition of Done
- Admin sidebar shows “Credit Lots” and “Credit Transactions”.
- Views load with filters and pagination; records are non-editable.

