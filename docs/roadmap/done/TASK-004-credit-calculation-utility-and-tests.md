# TASK-004: Credit Calculation Utility and Tests

Epic Reference: docs/roadmap/epics/EPIC-001-story-points-credits-system.md (EPIC-001)

## Description
Provide a single source of truth to compute required Story Points for a story based on character count and unit size (1,000 chars per point, minimum 1). Include thorough tests.

## Plan
- Add `utils/credits.py` with `calculate_required_credits(text: str, unit_size=1000) -> int` using ceil division.
- Add tests under `tests/test_credits.py` covering boundaries (0, 1, 999, 1000, 1001, large sizes) and Unicode handling.
- Ensure config-driven unit size is respected in tests.

## Definition of Done
- Function returns expected values for boundary cases and general inputs.
- Tests pass and are deterministic.
- Utility is imported by controllers and routes in later tasks.
