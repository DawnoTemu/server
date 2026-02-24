# Story Points (Punkty Magii) – Business Model Overview
Story Points are the in-app currency users spend to generate narrated stories. They translate real provider costs (text-to-speech, storage, bandwidth) into a simple, predictable unit.

## Credits vs. Story Points
- **Same thing**: “Story Points” is the user-facing name; in code and APIs they are “credits.” One Story Point = one credit.
- **Where you see it**: Routes like `/me/credits`, the credit ledger tables, and config keys (`CREDITS_UNIT_LABEL`, `CREDITS_UNIT_SIZE`) use the term credits; UI copy and marketing say Story Points (Punkty Magii).
- **Ledger remains unchanged**: Grants, debits, refunds, and expirations all operate on credits; the label swap is presentation-only.

## Earning Points
- **Signup seed**: New accounts may receive an initial non-expiring grant (`source=free`, configurable via `INITIAL_CREDITS`).
- **Subscriptions**: Paid plans mint monthly lots (`source=monthly`) on each billing cycle; lots can be set to expire at the period end.
- **Top-ups/Promos**: Admin or promo-driven grants (`source=add_on`, `event`, `referral`) add points with optional expirations.

## Spending Points
- **Price per story**: `ceil(characters / 1,000)` Story Points, minimum 1 point per request. Text length is taken from the story body at the time of synthesis.
- **When charged**: Points are debited before queueing audio synthesis; if queueing or background processing fails, points are refunded automatically to the original lots.
- **Visibility**: Users can check balances and history via `/me/credits` and `/me/credits/history`; insufficient funds return HTTP `402`.

## What Drives Our Costs
- **TTS provider usage**: Cartesia/ElevenLabs bill per character or per second generated; longer stories cost more Story Points to cover this variable spend.
- **Storage & delivery**: Audio files are stored in S3; downloads/streaming incur S3 + bandwidth costs. Points price in this overhead.
- **Voice lifecycle**: Creating/maintaining cloned voices consumes provider quotas; Story Points help offset these operational costs.

This model keeps the user-facing experience simple (points) while aligning pricing with underlying variable costs (characters synthesized, storage, and delivery).
