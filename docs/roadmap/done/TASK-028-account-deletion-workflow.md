# TASK-028: Account Deletion Workflow

Epic Reference: docs/roadmap/epics/EPIC-003-user-self-service-account-management.md (EPIC-003)

## Status
Done

## Description
Implement a self-service `DELETE /auth/me` flow that confirms the user’s identity, removes or anonymizes owned data (voices, audio stories, credits), and cleans up external resources to honor account deletion requests.

## Outcome
- Added `UserController.delete_account`, validating the current password before delegating to the data-layer cleanup routine and returning structured responses (including warnings when soft failures occur).
- Extended `routes/auth_routes.py` with `DELETE /auth/me`, wiring the new controller under `token_required`.
- Implemented `UserModel.delete_user`, which now removes user-generated audio (`AudioModel.delete_audio_for_user`), purges voices via direct S3/API cleanup, clears credit lots/transactions, nulls voice slot references, and deletes the user while handling warnings.
- Introduced `AudioModel.delete_audio_for_user` for user-scoped audio cleanup, reused by account deletion.
- Documented the endpoint in `docs/openapi.yaml` (`DeleteAccountRequest`/`DeleteAccountResponse`) and `docs/api.doc.md`, explaining request/response structure and error conditions.
- Added pytest coverage for deletion routes (`tests/test_routes/test_auth_routes.py`) and the model cleanup (`tests/test_models/test_user_model.py`), mocking external providers (S3, voice service) to keep tests deterministic.

## Definition of Done
- `DELETE /auth/me` requires password confirmation and responds with a clear success message. ✅
- Associated data (voices, audio stories, credit lots/transactions) is removed or anonymized according to the agreed strategy without foreign-key failures. ✅
- S3 cleanup routines are invoked (mocked in tests) and any failures are surfaced or retried. ✅
- Tests covering deletion success and error cases (wrong password, unexpected cleanup issue) pass (`pytest tests/test_routes/test_auth_routes.py tests/test_models/test_user_model.py`). ✅
