# Codebase Review

## 1. High-Level Overview
- Flask API with JWT auth generates narrated stories; credits (“Story Points”) are debited when queueing synthesis and refunded on failure. Ledger is modeled via `credit_transactions`, `credit_lots`, and `credit_transaction_allocations`, with calculators in `utils/credits.py` and user-facing endpoints in `routes/billing_routes.py`.
- Debits occur in `AudioController.synthesize_audio` before enqueuing Celery work; refunds are attempted in `tasks/audio_tasks.py` on task failures. Admins grant credits via `/admin/users/<id>/credits/grant`; monthly grants and expirations run in `tasks/billing_tasks.py`.
- Overall: core pieces exist, but balances are inaccurate when lots expire, ledger operations are weakly validated and loosely transactional, and test coverage for the credit system is minimal—insufficient for production.

## 2. Architecture & Design
- Architecture: `models/credit_model.py` holds ledger operations (grant/debit/refund, summaries), `utils/credits.py` exposes unit sizing/priority, controllers call these directly, and background tasks mutate lots. Cached balance lives on `users.credits_balance`.
- Strengths: Separate lot+transaction tables with allocation mapping and a partial unique index on open debits (via migrations). Source-priority ordering exists.
- Weaknesses: `credits_balance` is treated as a cache but never reconciled; expiry and balance computation paths are disconnected. Ledger functions commit internally, making it hard to compose atomic flows or reuse transactions. Source values and expirations are unvalidated free-form strings/naive datetimes. No single “CreditService” boundary—controllers, tasks, and admin actions each mutate state differently (e.g., sweeper vs. admin expire) which risks drift.
- Improvements: Introduce a ledger service with explicit transactional boundaries and shared validation (source enum, timezone-aware expirations). Make balance a derived value (or recompute on mismatch) instead of trusting cached fields. Normalize how grants/expirations write allocations and adjust balances. Use row locks or versioning on lots when sweeping or debiting.

## 3. Feature Implementation Review
- Flow: `AudioController.synthesize_audio` computes required credits (`calculate_required_credits`), sets audio to PENDING, calls `credit_debit`, then queues the Celery task (controllers/audio_controller.py:90-188). Task failures call `refund_by_audio` (tasks/audio_tasks.py).
- User endpoints: `/me/credits` returns balance, lots, and history (`routes/billing_routes.py`), but the balance is derived in `get_user_credit_summary` (models/credit_model.py:186-233).
- Bugs/edge cases:
  - Expired lots inflate balances: `get_user_credit_summary` sums **all** lots, including expired ones (models/credit_model.py:196-207). Users can see a higher balance than spendable, leading to 402s despite “enough” points.
  - Debit/queue saga is non-atomic: `credit_debit` commits before queueing; failure paths rely on best-effort refunds (controllers/audio_controller.py:111-188). If refund fails or tasks crash after debit, the user stays charged.
  - Expiration sweeper races: `expire_credit_lots` zeroes lots and adjusts cached balances without locking the user or reconciling with in-flight debits (tasks/billing_tasks.py:77-139), risking balance drift.
  - Grants don’t record allocations to the lot, so the ledger can’t trace which credit transaction funded which lot, weakening auditability (models/credit_model.py:236-264).
  - Source/expires are unchecked; any string or naive datetime is accepted (admin route controllers/admin_routes.py:191-245), inviting inconsistent data.
- Robustness gaps: No retry/idempotency around monthly grants per user beyond a naive created_at check; no self-healing when cached balance and computed balance diverge (only logs a warning).

## 4. Code Quality & Maintainability
- Readability is reasonable, but business rules are scattered. Key smells:
  - Internal commits in `grant`, `debit`, `refund_by_audio` prevent composing multi-step transactions and make error handling brittle.
  - Cached vs. computed balance mismatch is only logged; code still returns the (wrong) computed value with no reconciliation or metric (models/credit_model.py:205-233).
  - Lack of validation/normalization for sources and expirations encourages data drift; no constants/enums.
  - Tests don’t exercise the ledger paths—only trivial calculator and summary checks (tests/test_credits.py, tests/test_models/test_credit_model.py), so regressions would slip through.
- Refactors: Extract a `CreditService` with explicit transaction scopes, validation, and a single reconciliation path. Represent sources as an enum and validate inputs. Move cache reconciliation into reads (compute active balance, optionally update `credits_balance`). Add allocation records for grants/expirations to keep the ledger consistent.

## 5. Error Handling, Logging & Observability
- Logging is minimal around ledger mutations; debits that fail to refund log errors but don’t emit metrics or alerts (controllers/audio_controller.py:126-188). Sweeper silently adjusts balances without surfacing mismatches.
- No structured errors/metadata (user_id, lot_ids, tx_id) in logs; debugging mischarges will be painful. No metrics for debit/refund success, balance mismatches, expirations processed, or refund failures.
- Improve by adding structured logs and counters/timers around debit/refund/grant/sweeper paths, and emitting a reconciliation metric when cached vs computed diverge.

## 6. Performance & Scalability
- `/me/credits` loads **all** lots and counts all transactions (`query.count()`), with no pagination on lots; this will degrade with large ledgers. History is paged, but lots are not.
- `expire_credit_lots` and `grant_monthly_credits` load all candidates into memory and process in Python—no batching or pagination; this won’t scale.
- Counting before fetching (`query.count()`) on large ledgers is expensive. Consider paginating lots, limiting history defaults, and batch-processing sweeps/grants.

## 7. Security & Reliability
- JWT refresh tokens are stateless and not rotated/revocable; compromise cannot be contained without rotating `SECRET_KEY`. No per-device tracking.
- Ledger reliability: sweeper races with debits, grants, and admin actions because no locking/versioning on lots, and cached balances can be wrong for long periods. Refunds can restore credits to expired lots, effectively reactivating them.
- Admin credit grants accept arbitrary sources and expirations; malformed data could bypass intended consumption priority/expiry policy.

## 8. Testing Strategy
- Current coverage is shallow: calculator boundaries and a simple summary mismatch check; controller tests stub out `credit_debit` and never exercise ledger behavior. No tests for insufficient balance (402), allocation priority, refund idempotency, sweeper correctness, or monthly grant idempotency.
- Add unit tests for `debit` allocation ordering, insufficient balance, existing debit top-ups, refund idempotency returning to the same lots, and grant/allocation creation. Integration tests for `/me/credits` with expired lots, 402 on debit when balance < required, sweeper behavior, and admin grant validations. Property tests around cache vs. computed reconciliation.

## 9. Migration / Rollout / Ops Considerations
- Partial unique index on open debits exists only in Alembic migrations; ensure production is on Postgres (SQLite dev won’t enforce) and migrations are applied. Cached balances may already be wrong due to expired lots—add a one-off reconciliation job before rollout.
- Celery beat must run for monthly grants/expiration; defaults disable monthly grants (`MONTHLY_CREDITS_DEFAULT=0`), so monitor configuration. Add runbooks for reconciling balances, retrying failed refunds, and investigating ledger drift.

## 10. Actionable Plan to Production-Ready
- **Phase 1 (P0 – correctness/stability)**
  - Fix balance computation to exclude expired lots and optionally backfill `credits_balance` to the active sum; add reconciliation logging/metric (models/credit_model.py:196-233). Difficulty: medium, Priority: P0.
  - Make debit+queue path transactional or add a compensation guard (e.g., wrap debit + queue in one transaction or ensure refunds cannot fail silently; controllers/audio_controller.py:111-188). Difficulty: medium, Priority: P0.
  - Add locking/version checks to expiration sweeper and align it with active balance computation; batch process to avoid races and scale (tasks/billing_tasks.py:77-139). Difficulty: medium, Priority: P0.
- **Phase 2 (P1 – integrity/maintainability)**
  - Introduce `CreditService` with validated source enum/timezone-aware expirations; remove internal commits from ledger helpers so callers manage transactions. Difficulty: medium, Priority: P1.
  - Record allocations for grants/expirations to maintain an auditable ledger trail (models/credit_model.py:236-264, tasks/billing_tasks.py:77-139). Difficulty: medium, Priority: P1.
  - Reconcile cached balances on read or via a scheduled job; update `credits_balance` when mismatches are detected. Difficulty: low, Priority: P1.
  - Harden monthly grant idempotency (per-user window keyed by month + source) and add validation for admin grants (controllers/admin_routes.py:191-245). Difficulty: low, Priority: P1.
- **Phase 3 (P2 – observability/performance/security)**
  - Add structured logging and metrics for debit/grant/refund/sweeper paths; alert on refund failures and balance mismatches. Difficulty: low, Priority: P2.
  - Paginate lots in `/me/credits` and optimize history counting; batch sweeper/grant jobs. Difficulty: medium, Priority: P2.
  - Add refresh-token rotation/revocation (token store with jti/exp) and per-device invalidation; tighten rate limiting on credit-sensitive endpoints. Difficulty: medium, Priority: P2.
