# TASK-011: Monthly Grant Scheduler and Refresh Dates

Epic Reference: docs/roadmap/epics/EPIC-001-story-points-credits-system.md (EPIC-001)

## Description
Introduce a scheduler that grants monthly Story Points to subscribed users. Each grant creates a `credit_lots` entry with `source=monthly`, `amount_granted`, `amount_remaining`, and `expires_at` set to the next cycle. Users refresh on their subscription anniversary date.

## Plan
- Add a Celery beat schedule for a daily job that scans for users needing a monthly grant (based on `subscription_started_at` or similar; add field if missing later).
- Grant credits via `CreditModel.grant(user_id, amount, reason="monthly_grant", source="monthly", expires_at=<next refresh date>)`.
- Ensure idempotency for a given cycle (e.g., unique key on user_id + cycle window or application-level guard).
- Configuration: default monthly amount per plan (placeholder until subscription model lands).

## Definition of Done
- Scheduler creates monthly `credit_lots` for eligible users exactly once per cycle.
- Lots have correct `expires_at` and are visible via `/me/credits`.
- Tests cover scheduling boundaries and idempotency.

## Notes
- Subscription model wiring (eligibility and amounts) may be mocked initially and replaced later.
