# TASK-017: Admin UI — User Credits Detail Panel

Epic Reference: docs/roadmap/epics/EPIC-001-story-points-credits-system.md (EPIC-001)

## Description
Add a compact detail panel on the user view showing active credit lots and recent transactions to reduce context switching during support.

## Plan
- In `admin.py` `UserModelView`:
  - Add a custom view or inline panel that lists:
    - Active lots (source, amount_remaining, expires_at)
    - 20 most recent transactions (type, amount, status, reason, created_at)
  - Reuse ORM queries; avoid heavy joins. Keep read‑only.

## Definition of Done
- On a user’s detail page, admin can see active lots and recent transactions.
- No write controls are exposed in this panel.

