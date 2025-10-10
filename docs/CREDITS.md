# Story Points (Punkty Magii)

Story Points are the unit used to generate narrated stories. Longer texts cost more points; failed attempts are refunded automatically.

## How Points Are Used
- Price = ceil(characters / 1,000). Minimum 1 point.
- Example: 1–1,000 chars → 1 point; 1,001–2,000 → 2 points.
- Controller charges before queueing; if queueing or background processing fails, points are refunded.

## Credit Sources and Expiration
- Sources: event, monthly, referral, add_on, free.
- Expiration: monthly/event may expire; referral/add_on/free are typically non‑expiring.
- Consumption order: event → monthly → referral → add_on → free (soonest expiring first within a source).
- Refunds return points to the exact lots they were taken from.

## Checking Balance and Estimating Cost
- GET `/me/credits` (Bearer auth):
  - `{ balance, unit_label, unit_size, lots: [{source, amount_remaining, expires_at}], recent_transactions }`
- GET `/stories/{id}/credits`:
  - `{ required_credits }` for the selected story.

## Admin Grants
- POST `/admin/users/{user_id}/credits/grant` (admin):
  - Body: `{ amount, reason?, source?, expires_at? }`
  - Increases balance and creates a new credit lot.

## Errors and Refunds
- If insufficient points, the API returns `402 Payment Required`.
- Failures during synthesis (voice missing, API error, storage error, task crash) trigger an automatic refund.

## Examples
- A 4,500‑character story costs 5 points.
- Three such stories cost 15 points total.

