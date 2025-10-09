# TASK-008: Admin Grant Credits Endpoint

Epic Reference: docs/roadmap/epics/EPIC-001-story-points-credits-system.md (EPIC-001)

## Description
Allow admins to grant Story Points to a user account for support or promotional purposes. All grants must be recorded in the ledger.

## Plan
- Add `POST /admin/users/<user_id>/credits/grant` with body `{ amount, reason }`.
- Authenticate and authorize admin users; reuse existing admin blueprint.
- Use `CreditModel.grant(user_id, amount, reason)`; return updated balance and transaction id.
- Add tests for authorization, validation, and grants.

## Definition of Done
- Endpoint restricted to admins; returns updated balance and transaction record.
- Negative or zero amounts are rejected.
- Tests cover happy path and auth failures.
