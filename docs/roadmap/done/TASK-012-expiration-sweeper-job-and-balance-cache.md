# TASK-012: Expiration Sweeper Job and Balance Cache

Epic Reference: docs/roadmap/epics/EPIC-001-story-points-credits-system.md (EPIC-001)

## Description
Implement a daily job to expire `credit_lots` at `expires_at`, and ensure `users.credits_balance` reflects only active, non-expired lots. Decide whether to maintain the balance as a cache or compute on-read.

## Plan
- Add Celery beat entry for an expiration sweeper that:
  - Finds lots with `expires_at <= now` and `amount_remaining > 0`.
  - Marks them expired (implicitly by time) and adjusts `users.credits_balance` (if using cached approach).
  - Optionally records an informational `credit_transactions` item of type `expire` with zero net effect (for audit) or just relies on lot timestamps.
- Ensure concurrent operations are safe with row locks on affected users/lots.
- Add metrics/logs for visibility.

## Definition of Done
- Lots past `expires_at` are excluded from balance calculations and `/me/credits` responses.
- Cached balance (if used) stays consistent after sweeps and debits/refunds.
- Tests simulate expiration and verify balances and endpoints.

## Notes
- If computing balance on read, the sweeper may only be responsible for cleanup/logging.
