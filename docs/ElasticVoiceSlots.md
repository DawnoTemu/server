# Elastic Voice Slots Runbook

This document explains how DawnoTemu allocates, queues, and evicts ElevenLabs voice slots now that recording uploads are decoupled from remote slot usage. It is intended for engineers, product, support, and UX so everyone understands the lifecycle and customer messaging.

## 1. Lifecycle States

| State | Description | API Surfaces |
|-------|-------------|--------------|
| `recorded` | Voice has a stored sample but no remote slot | `Voice.status=recorded`, `Voice.allocation_status=recorded` |
| `allocating` | A Celery task is activating the ElevenLabs voice | `Voice.allocation_status=allocating`; audio POST returns `status=allocating_voice` |
| `ready` | Remote voice exists and can generate audio immediately | Audio POST returns `status=processing` or `ready`; `Voice.elevenlabs_voice_id` is populated |
| `cooling` | Optional warm-hold window before eviction (configured by `VOICE_WARM_HOLD_SECONDS`) | Present in DB, treated as ready but eligible for eviction |
| `evicted` | Voice was released to free a slot | `Voice.allocation_status=recorded`, `Voice.elevenlabs_voice_id` cleared |

Slot events are recorded in `voice_slot_events` with types such as `allocation_queued`, `allocation_started`, `allocation_completed`, `slot_evicted`, and `slot_lock_released`.

## 2. Audio Request Flow

1. **Client POST** `/voices/{voice_identifier}/stories/{story_id}/audio`
   - Accepts either the external ElevenLabs ID or the internal numeric voice ID (string path parameter).
2. **Controller** calls `VoiceSlotManager.ensure_active_voice`:
   - If a slot is available, the voice is marked `allocating` and the Celery allocation job is queued.
   - If the remote voice already exists, we proceed directly to audio synthesis.
3. **Credits** are debited synchronously; insufficient balance returns HTTP `402` immediately.
4. **Response Payload** (202):
   ```json
   {
     "id": 301,
     "status": "allocating_voice",
     "message": "Voice allocation is in progress",
     "voice": {
       "voice_id": 17,
       "queue_position": 2,
       "queue_length": 5,
       "allocation_status": "allocating"
     }
   }
   ```
   - Headers include `X-Voice-Queue-Position`, `X-Voice-Queue-Length`, and `X-Voice-Remote-ID` when known.
5. **Celery Task** polls for allocation completion. Once the voice is ready it synthesises audio, stores the file in S3, and updates `Voice.last_used_at`.

## 3. Queue Behaviour & Fairness

- Slots are capped by `ELEVENLABS_SLOT_LIMIT`. When capacity is exhausted, new voices enter a Redis-backed queue (`VoiceSlotQueue`) ordered by request time.
- The queue payload persists voice/user metadata and retry counts so idle reclaim can prioritise the longest-waiting voices.
- Warm hold: `VOICE_WARM_HOLD_SECONDS` keeps a voice “hot” after use. The reclaim task (`voice.reclaim_idle_voices`) evicts voices when they are older than the warm-hold window and not currently locked.
- Evictions and allocation attempts are logged to `voice_slot_events` for auditing and metrics.

## 4. Admin & Observability

- `GET /admin/voice-slots/status` (admin bearer token) returns:
  - `metrics`: slot limit, ready count, allocating count, queue depth, remaining capacity.
  - `active_voices`: last-updated voices holding or seeking slots.
  - `queued_requests`: Redis queue snapshot (voice id, attempts, score).
  - `recent_events`: 50 most recent slot events.
- `POST /admin/voice-slots/process-queue` schedules an immediate queue processing run (returns 202 with optional Celery task id).
- Celery beat triggers:
  - `voice.process_voice_queue` at `VOICE_QUEUE_POLL_INTERVAL` (default 60s) to work through queued allocations.
  - `voice.reclaim_idle_voices` every 5 minutes to free stale slots.

## 5. Front-End Messaging

Recommended strings (Polish-friendly):

| Status | Copy | Guidance |
|--------|------|----------|
| `queued_for_slot` | “Twoja prośba jest w kolejce. Przydzielimy slot głosowy w ciągu kilku chwil.” | Display queue position if available (`voice.queue_position`). |
| `allocating_voice` | “Twój głos jest aktywowany w ElevenLabs… odtwarzanie rozpocznie się automatycznie.” | Show spinner; retry automatically via polling POST. |
| `processing` | “Generujemy opowieść w Twoim głosie. To zwykle trwa ok. 30–90 sekund.” | Disable multiple submissions; audio task is already running. |
| `ready` | “Nagranie jest gotowe – możesz teraz odtworzyć historię.” | Provide play/download CTAs. |

If a retry is required (e.g., status `error` in audio polling), direct users to retry the POST; credits are already held and will not be double-charged.

## 6. Support & Troubleshooting

- **Why am I stuck in queue?** Check `/admin/voice-slots/status` for queue length and capacity. Encourage users to retry later if the queue length is large.
- **Audio shows error after allocation timeout?** The Celery task retries automatically. If repeated failures occur, inspect `voice_slot_events` and Sentry traces, then manually requeue the voice (`voice.process_voice_queue`) or allocate a new slot.
- **Remote voice missing?** If `Voice.elevenlabs_voice_id` is empty while status says `ready`, the allocation likely failed; the controller will respond 409 with error details so clients can trigger re-recording.

For deeper architectural context or emergency playbooks, contact the platform engineering team.
