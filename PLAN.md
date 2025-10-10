# Task & Context
Implement a credit-based system (public label: "Story Stars"; internal: credits) for story audio generation. Each story consumes credits based on text length: ceil(char_count / 1000). Deduct credits when queueing synthesis; refund on technical failure. Subscription plans may follow later.

## Current State (codebase scan)
- API flow: `routes/audio_routes.py` -> `AudioController.synthesize_audio` -> `AudioModel.synthesize_audio` -> Celery `tasks/audio_tasks.py`.
- Data models: `models/user_model.py` (no credits field), `models/story_model.py` (has `content`), `models/audio_model.py` (audio job records), `database.py` (SQLAlchemy setup), Alembic under `migrations/`.
- Auth & ownership: `utils/auth_middleware.py` used in audio routes.
- Tests: `tests/` includes endpoint and service tests; pytest configured via `pytest.ini`.

## Proposed Changes (files & functions)
- Schema/migrations:
  - Add `users.credits_balance` (int, default 0).
  - Add `audio_stories.credits_charged` (int, nullable).
  - New table `credit_transactions` with fields: `id`, `user_id`, `amount` (signed int), `type` (`debit`|`credit`|`refund`), `reason` (str), `audio_story_id` (nullable), `story_id` (nullable), `status` (`applied`|`refunded`), `metadata` (JSON), timestamps. Unique index to prevent duplicate debits per `audio_story_id`.
- Business logic:
  - New `models/credit_model.py` with `CreditModel.debit(user_id, amount, reason, audio_story_id, story_id)`, `CreditModel.refund_by_audio(audio_story_id, reason)`, `CreditModel.grant(user_id, amount, reason)`. Use row lock (`SELECT FOR UPDATE`) on `User` to ensure atomic balance updates.
  - Utility `utils/credits.py`: `calculate_required_credits(text: str, unit_size=1000) -> int` (ceil, min 1).
- Controller changes:
  - `controllers/audio_controller.py::synthesize_audio`: compute `required = calculate_required_credits(text)`. If audio already READY -> do not charge. If PROCESSING -> do not charge. For new/failed -> within one DB transaction: set audio status to PENDING, set `credits_charged = required`, attempt `CreditModel.debit(...)`. On insufficient balance -> rollback and return 402 with message.
- Task changes:
  - `tasks/audio_tasks.py`: on any failure (including `on_failure`), call `CreditModel.refund_by_audio(audio_story_id, reason="synthesis_failed")` if not already refunded; leave successful runs as-is (no extra action).
- Routes/endpoints:
  - `routes/billing_routes.py` (new blueprint):
    - `GET /me/credits` (auth) -> `{ balance, unit_label: "Story Stars" }` and optional recent transactions.
    - `GET /stories/<id>/credits` -> `{ required_credits }` based on stored `content`.
  - Admin: `POST /admin/users/<user_id>/credits/grant` with `{ amount, reason }` to grant credits.
- Config:
  - `Config.INITIAL_CREDITS` (default 0), `Config.CREDITS_UNIT_SIZE=1000`.
- Docs: `docs/CREDITS.md` explaining the model, examples, refund policy; update `README.md` briefly.
- Tests:
  - New `tests/test_credits.py`: unit tests for calculator and debit/refund logic.
  - Endpoint tests: insufficient credits returns 402; successful debit on queue; no double-charge when status is READY/PROCESSING; refund on task failure.

## Step-by-Step Plan
1) Add `utils/credits.py` with calculator + tests.
2) Alembic migration: add user and audio columns; create `credit_transactions`.
3) Implement `models/credit_model.py` (ledger + atomic debit/refund/grant).
4) Wire `AudioController.synthesize_audio` to calculate, debit, and set `credits_charged` atomically.
5) Update Celery task failure paths to trigger refund by `audio_story_id`.
6) Add `routes/billing_routes.py`, register blueprint, and admin grant endpoint.
7) Seed `INITIAL_CREDITS` in `UserModel.create_user`.
8) Write tests (calculator, debit/refund, endpoints, admin grant).
9) Update docs and minimal README note.

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
- Final public unit name (Story Stars, Story Points, Fairy Dust?).
Story Points (in polish Punkty Magii)
- Default `INITIAL_CREDITS` for new users and dev/test values.
Default INITIAL_CREDITS should be abotu 10 so we can generate 2 5 minutes stories.
- Should we expose transaction history to end users now?
Yes
- Any max story length or per-request cap to prevent surprise charges?
No
- Future: monthly subscription allotments and expiration order of credits.

