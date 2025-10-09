# TASK-010: Data Backfill — Initial Credits for Existing Users

Epic Reference: docs/roadmap/epics/EPIC-001-story-points-credits-system.md (EPIC-001)

## Description
Existing users created before the credits system should receive the default initial balance (10 Story Points). Perform a safe, idempotent backfill.

## Plan
- Migration or one-off script:
  - Set `users.credits_balance = 10` where `credits_balance IS NULL OR credits_balance = 0` and the account is active (optional).
  - Make the operation idempotent and safe to rerun.
- Add a dry-run mode for the script to report affected rows in non-prod.
- Record an informational `credit_transactions` entry per user with reason `initial_grant` where balance increased.

## Definition of Done
- Existing users receive 10 Story Points without duplicating grants on reruns.
- Ledger entries exist for grants applied.
- Script/migration documented with run instructions.
