# TASK-014: Admin UI — Display User Balance

Epic Reference: docs/roadmap/epics/EPIC-001-story-points-credits-system.md (EPIC-001)

## Description
Expose each user’s current Story Points (`credits_balance`) directly in the admin dashboard to improve visibility when supporting customers.

## Plan
- In `admin.py` `UserModelView`:
  - Add read-only column `credits_balance` to `column_list` and detail views.
  - Add description/help text for the field.
  - Ensure list view is sortable and filterable by balance if feasible.
- Verify no write paths modify `credits_balance` directly from the UI.

## Definition of Done
- Admin list shows `credits_balance` for each user.
- User detail view shows `credits_balance` with a short description.
- No edit form exposes `credits_balance` as writable.

