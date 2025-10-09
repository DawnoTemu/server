# TASK-009: Documentation and README Updates

Epic Reference: docs/roadmap/epics/EPIC-001-story-points-credits-system.md (EPIC-001)

## Description
Document the Story Points system for users and contributors, including pricing logic, examples, refund policy, and API references.

## Plan
- Create `docs/CREDITS.md` describing:
  - What are Story Points (Punkty Magii).
  - How they are consumed (1 point per 1,000 characters, ceil).
  - Expiration model: which sources expire (monthly/event) vs which do not (referral/add-on/free), and allocation order.
  - Refunds for technical failures (refunded to original lots).
  - Examples of usage, multi-story totals, and allocation examples.
- Update `README.md` with a brief overview and links to new endpoints.
- Update API docs (`docs/openapi.yaml` if maintained) with new routes and 402 error.

## Definition of Done
- `docs/CREDITS.md` exists with clear, concise guidance and examples.
- `README.md` references Story Points and the new endpoints.
- API docs updated or a follow-up task filed if out of scope.
- Documentation calls out `referral` credits, typical non-expiring policy, and their priority (`event -> monthly -> referral -> add_on -> free`).
