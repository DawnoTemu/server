# TASK-025: Documentation & UX Updates

Epic Reference: docs/roadmap/epics/EPIC-002-elastic-elevenlabs-voice-slots.md (EPIC-002)

## Description
Revise API documentation, README guidance, and user messaging so the new queue/allocate workflow is clearly communicated to both developers and end users.

## Plan
- Update `docs/openapi.yaml` with new or modified endpoints, response schemas (including `allocating_voice` / `queued_for_slot` statuses), and admin observability routes.
- Refresh README voice sections to explain the recording-only flow, just-in-time allocation, and privacy posture (encrypted storage).
- Author `docs/ElasticVoiceSlots.md` summarising lifecycle states, queue behaviour, fairness policy, and warm-hold rules.
- Provide UX copy recommendations for the frontend (“Queued”, “Allocating voice”, “Generating”) based on API responses.
- Coordinate with support/product to ensure help articles or FAQs reflect the new behaviour.

## Definition of Done
- OpenAPI spec validates successfully and reflects every new/changed endpoint and response contract.
- README and new documentation outline recording storage, slot allocation, eviction rules, and user-visible states.
- Product/UX teams have vetted the status messaging and queue explanations.
- Any customer-facing communication templates are updated to mention the queued allocation experience.*** End Patch
