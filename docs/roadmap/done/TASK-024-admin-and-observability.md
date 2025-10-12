# TASK-024: Admin & Observability Enhancements

Epic Reference: docs/roadmap/epics/EPIC-002-elastic-elevenlabs-voice-slots.md (EPIC-002)

## Description
Provide operational visibility into slot usage, queue depth, and eviction activity so support and engineering can monitor fairness and diagnose issues quickly.

## Plan
- Extend Flask-Admin (or build dedicated routes) to list active voices, queued requests, and recent slot events with filtering by user/status.
- Surface key metrics (slot utilisation, queue length, eviction counts) via logging structure or StatsD-compatible hooks.
- Add admin actions to manually retry stuck queue items or safely evict a specific voice when necessary.
- Ensure API responses include optional debug headers (e.g., queue position) for internal tooling.
- Document operational runbooks covering manual eviction and interpreting dashboard data.

## Definition of Done
- Admin interface (or JSON endpoints) shows current slots, queue entries, and latest evictions.
- Structured logs/metrics allow alerting on approaching slot limits or long queue times.
- Manual remediation actions are gated behind admin auth and respect locking safeguards.
- Operational documentation is updated in `docs/ElasticVoiceSlots.md` or a related runbook.*** End Patch
