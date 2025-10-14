# TASK-029: Credit Summary & History API Enhancements

Epic Reference: docs/roadmap/epics/EPIC-003-user-self-service-account-management.md (EPIC-003)

## Status
In Progress

## Description
Upgrade the credit endpoints so users can view their active lot balances, upcoming expirations, and a paginated transaction history that surfaces debits, credits, expirations, and refunds with relevant metadata.

## Plan
- Add read-model helpers in `models/credit_model.py` to aggregate balances, lot details, and transaction history with pagination and filtering.
- Expand `routes/billing_routes.py` (and related controllers) to expose enriched `/me/credits` output and/or a dedicated `/me/credits/history` endpoint with query parameters.
- Update shared utilities to format credit responses consistently (unit labels, sources, expiration data) and document payload structures.
- Cover new behavior with pytest route tests, including pagination boundaries, filtering options, and data-shaping assertions.

## Definition of Done
- Credit endpoints return balance, current lots (with source and expiry), and transaction history respecting pagination defaults and limits.
- Empty states (no transactions, expired lots) are handled gracefully without errors.
- Documentation (OpenAPI + Markdown) reflects new response fields and query params.
- Tests validating credit summaries/history pass (`pytest tests/test_routes/test_billing_routes.py`).*** End Patch
