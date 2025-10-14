# TASK-027: User Profile Update Endpoints

Epic Reference: docs/roadmap/epics/EPIC-003-user-self-service-account-management.md (EPIC-003)

## Status
Done

## Description
Deliver a secure `PATCH /auth/me` endpoint that lets authenticated users change their email and/or password after confirming their current password, while ensuring downstream models, tokens, and notifications stay consistent.

## Outcome
- Added a `UserController.update_profile` helper to verify the current password, enforce email uniqueness, reset the email confirmation flag, and send confirmation emails when the address changes.
- Registered `PATCH /auth/me` in `routes/auth_routes.py`, requiring `token_required` and returning structured response metadata (confirmation status, password update flag).
- Documented the new contract in OpenAPI (`UpdateProfileRequest`/`UpdateProfileResponse`) and refreshed the API docs with examples.
- Added pytest coverage (`tests/test_routes/test_auth_routes.py`) for successful updates and validation failures (missing password, incorrect password, duplicate email). Tests run via `pytest tests/test_routes/test_auth_routes.py`.

## Definition of Done
- `PATCH /auth/me` accepts email and password updates, requiring the current password and blocking duplicate emails. ✅
- Updated user details are persisted and reflected in the API response; follow-up actions (email confirmation status, token handling) are documented or stubbed. ✅
- Negative scenarios return appropriate 4xx responses with helpful error messages. ✅
- Tests covering controller/model logic and the route pass (`pytest tests/test_routes/test_auth_routes.py`). ✅
