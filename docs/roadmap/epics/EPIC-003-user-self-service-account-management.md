# Task & Context
Extend the authenticated customer API so members can manage their own account details (email and password), delete their account, and review a comprehensive credit balance that includes slot expirations and transaction history.

## Current State (codebase scan)
- `routes/auth_routes.py` provides registration, login, refresh, password reset, and `GET /auth/me`, backed by `controllers/auth_controller.AuthController`; no profile-edit or self-deletion endpoints exist.
- `models/user_model.py` exposes helpers for creating users, confirming email, updating passwords, and toggling activation/admin flags, but lacks email update or cascading delete operations.
- `routes/billing_routes.py` returns a lightweight `/me/credits` view using `CreditLot` and `CreditTransaction`, without pagination or full history, and no endpoint to request deeper credit data.
- `models/credit_model.py` handles grants/debits/refunds but offers no read-model helpers for summarizing lots or transactions.
- User-owned resources span `models/voice_model.py` (voices, slot events) and `models/audio_model.py` (audio stories); there is no centralized cleanup routine for deleting a user and owned content.
- Tests cover present auth and credit flows but do not exercise profile updates, account deletion, or enhanced credit history responses.

## Proposed Changes (files & functions)
- Introduce `controllers/user_controller.py` (or equivalent) to manage profile updates and account deletion, enforcing current-password verification and orchestrating downstream operations.
- Enhance `models/user_model.py` with `update_email`, improved `update_password` feedback, and a `delete_user` method that reliably removes (or anonymizes) data while respecting foreign-key constraints.
- Add helper utilities to `models/voice_model.py` and `models/audio_model.py` for bulk cleanup of a user’s assets without redundant external API calls.
- Extend `models/credit_model.py` with read-side helpers (`get_user_credit_summary`, `get_user_transactions`) that support pagination, ordering, and aggregation of lot metadata (source, granted, remaining, expiration).
- Expand `routes/auth_routes.py` with authenticated `PATCH /auth/me` and `DELETE /auth/me` endpoints leveraging the new controller logic.
- Broaden `routes/billing_routes.py` to return richer credit information or add `/me/credits/history` with query parameters for paging and filtering.
- Document the API changes in `docs/openapi.yaml` and `docs/api.doc.md`, including payloads for profile updates, account deletion confirmation, and extended credit history responses.
- Update or add pytest suites (routes/controllers/models) to cover profile changes, account deletion, and credit history retrieval, mocking external integrations where needed.

## Step-by-Step Plan
1. Confirm product expectations: email-change flow (re-verification, token refresh), deletion semantics (soft vs hard delete), and credit history pagination defaults.
2. Implement user model helpers for updating email/password and deleting users, plus utility functions for cleaning up dependent resources and credit data.
3. Build a dedicated controller/service to validate inputs, enforce password confirmation, and coordinate email notifications or token refreshes as required.
4. Wire new `/auth/me` PATCH/DELETE endpoints and enhance billing routes for credit summary/history, ensuring `token_required` guards and consistent response schemas.
5. Update OpenAPI specification and supporting docs to reflect new endpoints and response structures.
6. Add deterministic pytest coverage for the new flows (mocking email, S3, Cartesia/ElevenLabs) and verify failure scenarios (incorrect password, insufficient credits, expired lots).
7. Execute the relevant pytest subsets (auth, billing, credit models) and resolve regressions before release.

## Risks & Assumptions
- Product direction on email change confirmation, account deletion strategy (soft vs hard delete), and historical data retention is still pending.
- User deletion requires coordinated cleanup across voices, audio stories, credit lots/transactions, and possibly S3 assets; missing a dependency could leave orphaned data.
- Credit histories can grow large; pagination and filtering must be efficient to avoid heavy responses.
- Token/session invalidation after email change may be necessary; lack of clarity could cause inconsistent authentication state.
- External integrations (email providers, storage) must be mocked for tests to remain deterministic.

## Validation & Done Criteria
- PATCH and DELETE `/auth/me` endpoints behave as expected, requiring current-password verification and accurately mutating or removing user data.
- Credit summary/history endpoints return correct balances, lot expirations, and transaction lists with pagination controls.
- Cascading cleanup succeeds for user-owned resources without violating foreign-key constraints or leaving S3 objects behind (verified via unit/integration tests).
- OpenAPI documentation and Markdown guides reflect the final contract and are free of validation errors.
- `pytest` suites covering auth, billing, and credit models pass locally (e.g., `pytest tests/test_routes/test_auth_routes.py tests/test_routes/test_billing_routes.py`).

## Open Questions
- Should email changes require re-confirmation, and how should tokens be refreshed or revoked afterward?
- Is a soft-delete (deactivate/anonymize) acceptable, or must we fully purge data and S3 assets?
- What pagination defaults and maximums should apply to credit transaction history (page size, filtering by type/source)?
