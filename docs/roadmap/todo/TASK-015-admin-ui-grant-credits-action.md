# TASK-015: Admin UI — Grant Story Points Action

Epic Reference: docs/roadmap/epics/EPIC-001-story-points-credits-system.md (EPIC-001)

## Description
Add a friendly action in the admin user view to grant Story Points (amount, reason, source, optional expires_at) using the existing ledger logic.

## Plan
- In `admin.py` `UserModelView`:
  - Add a custom action/button “Grant Story Points”.
  - Provide a small form (modal) with fields: `amount` (int > 0), `reason` (text), `source` (select: referral/add_on/free/monthly/event), `expires_at` (ISO8601).
  - Call `CreditModel.grant(...)` directly or reuse `POST /admin/users/<id>/credits/grant`.
  - Flash success/error messages and reload list.
- Validate input and handle exceptions with rollback.

## Definition of Done
- Admin can grant points to a selected user via UI.
- Balance updates immediately after grant.
- Invalid input shows clear errors; no partial commits.

