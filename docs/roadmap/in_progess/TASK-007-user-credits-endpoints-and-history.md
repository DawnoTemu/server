# TASK-007: User Credits Endpoints and History Exposure

Epic Reference: docs/roadmap/epics/EPIC-001-story-points-credits-system.md (EPIC-001)

## Description
Expose account balance, recent transactions, and lot-level details (source, expiry) to end users, and provide an endpoint to estimate Story Points for a given story.

## Plan
- Add `routes/billing_routes.py` and register blueprint:
  - `GET /me/credits` (auth): returns `{ balance, unit_label, unit_size, lots: [{source, amount_remaining, expires_at}], recent_transactions: [...] }`. Lots include `referral` source entries, typically with `expires_at = null`.
  - `GET /stories/<id>/credits`: computes `{ required_credits }` using stored content length.
- Add tests to validate payload shape, auth requirements, and correctness.

## Definition of Done
- Endpoints return expected JSON and respect auth.
- Recent transactions include recent debits/refunds/credits with timestamps.
- Lots payload shows `source`, `amount_remaining`, and `expires_at` for each active lot.
- Tests validate both endpoints and error handling (unknown story -> 404).
