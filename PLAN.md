# Task & Context
- Extend the authenticated self-service API so users can update their profile (email/password), delete their account, and retrieve a richer credit overview including slot details and transaction history.

## Current State (codebase scan)
- `routes/auth_routes.py` exposes auth endpoints (register/login/reset) plus `GET /auth/me`, delegating to `controllers/auth_controller.AuthController`.
- `controllers/auth_controller.py` manages registration/login/token/password reset logic but no profile update or deletion functions.
- `models/user_model.py` defines the `User` ORM and `UserModel` helpers (create, confirm, update password, activate/deactivate/admin) yet lacks email-update or delete methods.
- `routes/billing_routes.py` provides `GET /me/credits`, querying `CreditLot` and `CreditTransaction` directly to return balance, active lots, and last 20 transactions.
- `models/credit_model.py` implements credit persistence (lots, transactions, grants/debits/refunds) but has no reusable read-side helpers for summaries/history.
- User-owned resources span `models/voice_model.py` (voices & slot events) and `models/audio_model.py` (audio stories) referencing `users.id` without a centralized cleanup path.
- Tests cover auth flow basics, utility functions, and various route/controller behaviors, but nothing exercises profile edits, account deletion, or detailed credit history.

## Proposed Changes (files & functions)
- `controllers/user_controller.py` (new) to encapsulate profile update & account deletion workflows, validating input/current password and coordinating downstream model operations.
- `controllers/auth_controller.py` to delegate new `/auth/me` operations to `UserController` and refresh returned user payloads/tokens when email changes.
- `models/user_model.py` to add `update_email`, refine `update_password` (optionally returning the updated user), and implement `delete_user` that clears dependent data safely.
- `models/voice_model.py` & `models/audio_model.py` to expose utilities for purging a user's voices/audio (reusing existing deletion logic without redundant external calls).
- `models/credit_model.py` to add read helpers (e.g., `get_user_credit_summary`, `get_user_transactions`) supporting pagination and exposing lot metadata (source/type, granted, remaining, expiry).
- `routes/auth_routes.py` to register `PATCH /auth/me` (profile updates) and `DELETE /auth/me` (account removal) under `token_required`.
- `routes/billing_routes.py` to extend `/me/credits` response or introduce `/me/credits/history` with configurable limits, leveraging the new credit helpers for consistent payloads.
- `docs/openapi.yaml` & `docs/api.doc.md` to document new endpoints, payload schemas, and enriched credit responses.
- `tests/test_routes/test_auth_routes.py` (new) plus updates in billing route/model tests to cover success/error cases for profile update, account deletion, and credit history retrieval.

## Step-by-Step Plan
1. Finalize request/response schema & security expectations (current password requirement, email change confirmation behavior, credit history pagination defaults).
2. Implement model-level helpers for email/password updates, credit summary queries, and user cleanup, with targeted unit tests where practical.
3. Build `UserController` (or extend existing controller) to orchestrate validation, invoke model helpers, and shape API responses/errors.
4. Wire new `/auth/me` PATCH/DELETE and enhanced credit endpoints through the Flask routes, ensuring authentication decorators and consistent responses.
5. Update OpenAPI + markdown docs to reflect the new contract, keeping schemas in sync with implementation.
6. Add pytest coverage for new behaviors (route/controller/model layers), mocking external services (email, S3, voice deletion) to keep tests deterministic.
7. Run focused pytest targets (`tests/test_routes/test_auth_routes.py`, billing-related suites) and resolve regressions.

## Risks & Assumptions
- Assume profile changes require the current password; unclear if email updates must trigger re-verification and token refresh.
- Cascading deletions must handle voices, audio stories, slot events, and credits to avoid FK conflicts; missing cleanup paths may break account deletion.
- Credit histories could be large; need sensible limits/pagination to prevent heavy responses while satisfying requirements.
- Token/session handling post-email change is unspecified; may need to invalidate/refresh tokens or document expectations.

## Validation & Done Criteria
- New and existing pytest suites covering auth/billing routes and model helpers pass locally (`pytest tests/test_routes/test_auth_routes.py tests/test_routes/test_billing_routes.py` plus impacted modules).
- Manual or scripted Flask client checks confirm profile update, account deletion, and credit history responses match documented schema.
- OpenAPI spec and docs build cleanly with updated endpoints/fields matching implementation.
- No regressions in existing authentication or credit flows; code adheres to project style guidelines.

## Open Questions
- Should changing the email require re-confirmation before it becomes active (and how to handle interim login state)?
Yes, after changing email we should logout user and ait for email confirmation 
- Is a soft-delete (mark inactive + anonymize) acceptable, or must we fully purge user data and S3 assets?
Fully purger for GDPR is must have. But user should be art that he./she will lost all the stories
- What pagination/limit expectations exist for the credit transaction history (default size, max cap, filtering by type/source)?
make something rationale