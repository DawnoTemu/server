# Task & Context
Implement a credit-based system (public label: "Story Stars"; internal: credits) for story audio generation. Each story consumes credits based on text length: ceil(char_count / 1000). Deduct credits when queueing synthesis; refund on technical failure. Subscription plans may follow later.

## Current State (codebase scan)
- API flow: `routes/audio_routes.py` -> `AudioController.synthesize_audio` -> `AudioModel.synthesize_audio` -> Celery `tasks/audio_tasks.py`.
- Data models: `models/user_model.py` (no credits field), `models/story_model.py` (has `content`), `models/audio_model.py` (audio job records), `database.py` (SQLAlchemy setup), Alembic under `migrations/`.
- Auth & ownership: `utils/auth_middleware.py` used in audio routes.
- Tests: `tests/` includes endpoint and service tests; pytest configured via `pytest.ini`.

## Proposed Changes (files & functions)
- Schema/migrations:
  - Add `users.credits_balance` (int, default 0; may act as cache).
  - Add `audio_stories.credits_charged` (int, nullable).
  - Add `credit_transactions` (ledger) with fields: `id`, `user_id`, `amount` (signed int), `type` (`debit`|`credit`|`refund`), `reason`, `audio_story_id` (nullable), `story_id` (nullable), `status` (`applied`|`refunded`), `metadata` (JSON), timestamps; unique index to prevent duplicate debits per `audio_story_id`.
  - Add `credit_lots` to support expirations and sources: `id`, `user_id`, `source` enum (`monthly`|`add_on`|`free`|`event`|`referral`), `amount_granted`, `amount_remaining`, `expires_at` (nullable), timestamps, indexes (`user_id, expires_at`).
  - Add `credit_transaction_allocations` to map debits/refunds to lots: `transaction_id`, `lot_id`, `amount` (signed), composite PK/index.
- Business logic:
  - New `models/credit_model.py` with operations: `debit(user_id, amount, reason, audio_story_id, story_id)` (allocates across lots by configured priority), `refund_by_audio(audio_story_id, reason)` (returns to original lots), and `grant(user_id, amount, reason, source, expires_at=None)` (creates/updates a lot).
  - Use row locks on `User` and selected `credit_lots` during allocation. Maintain `users.credits_balance` as cached sum of non-expired `amount_remaining` (or compute on read if preferred initially).
  - Utility `utils/credits.py`: `calculate_required_credits(text: str, unit_size=1000) -> int` (ceil, min 1).
- Controller changes:
  - `controllers/audio_controller.py::synthesize_audio`: compute required credits; skip charge if READY/PROCESSING; for new/failed -> set `PENDING` and `credits_charged`, then call `CreditModel.debit(...)`. Insufficient balance -> 402.
- Task changes:
  - `tasks/audio_tasks.py`: on failure (including `on_failure`), call `CreditModel.refund_by_audio(audio_story_id, reason="synthesis_failed")` (idempotent). Success path unchanged.
- Routes/endpoints:
  - `routes/billing_routes.py`:
    - `GET /me/credits` (auth) -> `{ balance, unit_label, unit_size, lots: [{source, remaining, expires_at}], recent_transactions }`.
    - `GET /stories/<id>/credits` -> `{ required_credits }`.
  - Admin: `POST /admin/users/<user_id>/credits/grant` with `{ amount, reason, source, expires_at? }`.
- Config:
  - `Config.INITIAL_CREDITS`, `Config.CREDITS_UNIT_SIZE=1000`, `Config.CREDITS_UNIT_LABEL`, and `Config.CREDIT_SOURCES_PRIORITY=["event","monthly","referral","add_on","free"]`.
  - Referral lots: typically non-expiring (no `expires_at`) and prioritized after monthly grants.
- Docs: `docs/CREDITS.md` explaining unit, calculation, allocation order, which sources expire (monthly/event) vs not (add_on/free), refund policy; update `README.md`.
- Tests:
  - Unit tests for calculator, debit/refund with lots, allocation priority, and idempotency.
  - Endpoint tests: 402 on insufficient funds; correct lots and recent transactions in `/me/credits`.

## Step-by-Step Plan
1) Add `utils/credits.py` with calculator + tests.
2) Alembic migration: add user/audio columns; create `credit_transactions`, `credit_lots`, and `credit_transaction_allocations` with indexes.
3) Implement `models/credit_model.py` (ledger + atomic debit/refund/grant) with lot allocation and idempotent refunds.
4) Wire `AudioController.synthesize_audio` to compute, allocate debit, set `credits_charged`, and queue task; handle 402.
5) Update Celery task failure paths to trigger lot-aware refund by `audio_story_id`.
6) Add `routes/billing_routes.py`, register blueprint; expose balance, lots, history; add admin grant endpoint with `source`.
7) Seed `INITIAL_CREDITS` in `UserModel.create_user` by creating a non-expiring `free` lot and adjusting cached balance.
8) Write tests (calculator, allocation priority, endpoints, admin grant, refund idempotency).
9) Update docs and minimal README note.
10) Future (post-MVP): scheduler to grant monthly lots and expiration sweeper.

## Risks & Assumptions
- Concurrency: two synth requests racing; solved via user row lock + unique debit per `audio_story_id`.
- Refund idempotency: ensure a single refund applies per audio story.
- Endpoint status code: use 402 Payment Required for insufficient credits.
- Text length source: use `Story.content` length; rounding is ceil(len(content)/1000), min 1.
- Debiting timing: charge only when a new job is queued (not when READY/PROCESSING).

## Validation & Done Criteria
- Migrations apply cleanly; new fields/tables exist.
- `POST /voices/{voice}/stories/{story}/audio`:
  - 202 and balance decreases by required credits when queueing new synthesis.
  - 200 and no charge when audio already READY.
  - 202 and no extra charge when already PROCESSING.
  - 402 with clear message when balance is insufficient.
- On task failure, user balance is fully refunded; ledger reflects debit + refund.
- `GET /me/credits` returns correct balance; admin grant works and is audited.
- Tests pass in CI (`pytest -v`).

## Open Questions
- Final public unit name: Story Points (Punkty Magii).
- Default `INITIAL_CREDITS`: 10 (enough for ~2 five-minute stories).
- Expose transaction history now: Yes.
- Max story length cap: No.
- Future: monthly subscription grants and expiration job (planned as TASK-011/012).
