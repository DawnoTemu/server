# TASK-001: Configure "Story Points (Punkty Magii)" and Initial Credits

Epic Reference: docs/roadmap/epics/EPIC-001-story-points-credits-system.md (EPIC-001)

## Description
Define the public credit unit label as "Story Points (Punkty Magii)" and configure credit unit sizing and initial balances. New users receive 10 Story Points by default. Expose these constants centrally for reuse across services and tests.

## Plan
- Add `Config.CREDITS_UNIT_LABEL = "Story Points (Punkty Magii)"` and `Config.CREDITS_UNIT_SIZE = 1000`.
- Add `Config.INITIAL_CREDITS = 10` (dev/prod default; override via env var if provided).
- Update `UserModel.create_user` to initialize `credits_balance` for new users.
- Provide a minimal helper to retrieve label/size for routes and UI.
- Update README to mention Story Points and the default balance.
 - Add `Config.CREDIT_SOURCES_PRIORITY = ["event", "monthly", "referral", "add_on", "free"]` with inline docs.
 - Document that `referral` lots are typically non-expiring and will be consumed after `monthly` but before `add_on` and `free`.

## Definition of Done
- Config contains `CREDITS_UNIT_LABEL`, `CREDITS_UNIT_SIZE`, and `INITIAL_CREDITS`.
- Config contains `CREDIT_SOURCES_PRIORITY` including `referral` in the agreed order.
- New users created in dev/test/prod start with `credits_balance = 10`.
- Unit tests cover config fallback and initialization.
- README includes Story Points description and defaults.

## Notes
- No story length cap per epic decision.
