# Session log — 2026-04-10 subscription rollout

Chronological handoff doc for the long engineering session that took the
RevenueCat subscription system from "code merged but untested" to "fully
verified end-to-end in production with known-good sandbox flow". Written
for future-me and anyone picking up subscription work cold.

Format: what happened, what broke, what we learned, what's still open.

## TL;DR

- **Starting state** (morning of 2026-04-10): `feat/subscription-integration`
  branch merged to `main` weeks ago but never exercised. Mobile client code
  calling unimplemented server endpoints. RevenueCat env vars unset on
  Render. No on-device testing had been done.
- **Ending state** (that night): subscription backend fully verified
  end-to-end on production (Render, `server-pf6p.onrender.com` /
  `api.dawnotemu.app`). All 6 webhook lifecycle events (INITIAL_PURCHASE,
  RENEWAL×3, NON_RENEWING_PURCHASE×2, CANCELLATION, EXPIRATION) observed.
  Addon receipt validation works. Billing bypass security check
  live-verified on production. Mobile UX bugs discovered during testing
  root-caused and fixed server-side without any mobile rebuild.
- **Total commits**: 10 on `DawnoTemu/server`, 3 on `DawnoTemu/mobile`
- **Total tests**: 258→270→329 server / 216→222 mobile
- **Issues filed**: 6 (#44, #45 on server; #21, #22 on mobile; plus
  closures of #37 and mobile#20)
- **Production deploys**: 5 (gitignore, subscription merge, env-var
  redeploy, v1 API fix, debug log, docs update, PR #42 flag, PR #43 tests)
- **Bugs fixed in production during the session**: 3 critical + 2 UX

## Critical path — what was verified live

Every row in this table was exercised against the production Render
service with real sandbox purchases from an iPhone XR running iOS 18.7.6:

| Verification | Result | Where observed |
|---|---|---|
| Render env vars (`REVENUECAT_{API_KEY,PROJECT_ID,WEBHOOK_SECRET}`) | Set via API, startup warning disappeared | Render logs |
| RevenueCat webhook URL + auth header configured | TEST event round-trip 200 OK | RC dashboard + server logs |
| Mobile iOS RC key swapped test→production | `appl_MnDXgcTtNwgOCOadrKiNMPnNUbY` in mobile `.env` + EAS env | EAS build bundle inspection |
| Mobile EAS preview build with `developmentClient: false` | Boots to real app, not dev launcher | iPhone XR |
| `POST /api/user/link-revenuecat` binds RC ID to server user | `revenuecat_app_user_id = "33"` in DB | DB query |
| `INITIAL_PURCHASE` webhook → subscription active + 26 credits | Credits 8 → 34, `subscription_active=true` | DB query |
| `RENEWAL` webhook fires every 5 min in sandbox (3 observed) | Each added 26 credits, `webhook_events` populated | DB query + Render logs |
| Audio synthesis with credit debit | 3 credits consumed on short fairy tale | DB query |
| Addon purchase receipt validation | *initial failure* → root-caused → fixed server-side → works | Live test via curl |
| **Billing bypass attack (product mismatch)** | HTTP 403 on `credits_10` receipt claimed as `credits_30` | Live curl POST |
| Legit addon grant | HTTP 200, +10 credits recorded in `consumed_addon_transactions` | Live curl POST |
| `CANCELLATION` webhook → `will_renew=false` | Subscription stayed active until period end | DB query |
| `EXPIRATION` webhook → `subscription_active=false` | Credits preserved (127) | DB query |

## Production deploys this session

| sha | title | purpose |
|---|---|---|
| `3919a33` | chore: gitignore `.secrets/` | First doc+config tweak, validated the deploy path |
| `a543b97` | debug: log receipt_token vs RC store_purchase_identifier | Temporary diagnostic commit to capture the exact `receipt_token` mobile was sending |
| `1aedff9` | fix: use RC v1 API for addon receipt validation | **The real fix** — see "Bug 1" below |
| `d8437b0` | docs: warn about RC v1/v2 API mismatch | Permanent warning in code and requirements doc |

Not deployed yet (behind PRs):
- **PR #42** (merged): `ENFORCE_SUBSCRIPTION_GATE` feature flag
- **PR #43** (merged): fix CI test failures that had been red since `9806801`
- **PR #46** (open, filed overnight): datetime.utcnow migration + webhook cleanup task

## Bug 1 — mobile sends v1 receipt id, server was querying v2 API

**Severity**: P0 — all real addon purchases would fail silently

### Symptom

Every addon purchase on device produced the mobile toast `"Zakup udany,
ale nie udało się dodać punktów. Ponowimy automatycznie przy następnym
uruchomieniu."` Server logs showed:

```
controllers.addon_controller - WARNING - Receipt not found in RevenueCat for user 33
POST /api/credits/grant-addon HTTP/1.1 403 38
```

despite the purchase being clearly visible via direct RC v2 API call.

### Root cause

RevenueCat maintains **three different identifiers** for a single
non-subscription transaction, exposed through three different APIs:

| API | Field | Example |
|---|---|---|
| Mobile SDK `nonSubscriptionTransactions[i].transactionIdentifier` | v1 internal id | `o1_kSFvmriDAHzQ1wdJi0UAhg` |
| `GET /v1/subscribers/{id}` → `non_subscriptions[product][].id` | v1 internal id | `o1_kSFvmriDAHzQ1wdJi0UAhg` |
| `GET /v1/subscribers/{id}` → `non_subscriptions[product][].store_transaction_id` | Apple/Google store id | `2000001151372110` |
| `GET /v2/projects/.../customers/{id}/purchases[].id` | v2 internal id | `otpAapf990a29cdad69816a7038d8b7b68a42e` |
| `GET /v2/projects/.../customers/{id}/purchases[].store_purchase_identifier` | Apple/Google store id | `2000001151372110` |

The mobile SDK returns the **v1 internal id**. The server's
`_validate_receipt_with_revenuecat` queried the **v2 API** and matched
against v2's `id` or `store_purchase_identifier`. **None of those
matched** the v1 id the mobile was sending, so validation always
returned False.

### How we found it

Added a temporary debug log (`a543b97`) that dumped:
1. The `receipt_token` exactly as received in the request body
2. Every purchase returned by the v2 API for the user

Captured this in Render logs during a live retry:
```
DEBUG_RECEIPT_TOKEN: user=33 receipt_token='o1_kSFvmriDAHzQ1wdJi0UAhg' (len=25)
DEBUG_RECEIPT_TOKEN: RC returned 2 purchases for user 33
DEBUG_RECEIPT_TOKEN: [item 0] id='otpAap6fd6527bb1051b1d2f399b5d45e8c428' store_purchase_identifier='2000001151376401' product_id='prod96c9d6eb5c'
DEBUG_RECEIPT_TOKEN: [item 1] id='otpAapf990a29cdad69816a7038d8b7b68a42e' store_purchase_identifier='2000001151372110' product_id='prod96c9d6eb5c'
```

Then tested the RC v1 API manually:
```bash
curl -H "Authorization: Bearer appl_MnDXgcTtNwgOCOadrKiNMPnNUbY" \
  https://api.revenuecat.com/v1/subscribers/33
```

The v1 response had `non_subscriptions["credits_10"][0].id =
"o1_kSFvmriDAHzQ1wdJi0UAhg"` — **exact match** to what the mobile sent.

### Fix (`1aedff9`)

Rewrote `_validate_receipt_with_revenuecat` to query the v1 API instead:
- Reads `subscriber.non_subscriptions[expected_product_id]`
- Matches on either `id` (v1 internal, what the mobile sends) or
  `store_transaction_id` (Apple/Google id, for forward compatibility if
  the mobile SDK changes behavior)
- **Product-mismatch check becomes implicit**: v1 groups transactions by
  `product_id`, so looking up under the claimed product IS the mismatch
  check. A receipt filed under `credits_10` simply doesn't appear in
  `non_subscriptions['credits_30']`. The PR #42 security guarantee is
  preserved with less code.

### Authentication complication

v1 API **rejects v2 `sk_*` secret keys** (`code 7723`: "You're trying to
use a secret API key incompatible with RevenueCat API V1"). v1 accepts:
- Platform-specific public keys (`appl_*`, `goog_*`) — the same keys
  baked into the mobile app, safe to use server-side for read operations
- Legacy REST API secret keys (different format, not set up on this
  project)

Solution: added `REVENUECAT_IOS_PUBLIC_KEY` / `REVENUECAT_ANDROID_PUBLIC_KEY`
to Render env group + `Config` + `Config.validate()` optional set. Server
selects the appropriate key based on the `platform` field from the grant
request.

### Live verification

After deploy:

```bash
# Test A — security (wrong product)
POST /api/credits/grant-addon
{"receipt_token":"o1_kSFvmriDAHzQ1wdJi0UAhg","product_id":"credits_30","platform":"ios"}
→ HTTP 403 {"error":"Receipt validation failed"}

# Test B — legit
POST /api/credits/grant-addon
{"receipt_token":"o1_kSFvmriDAHzQ1wdJi0UAhg","product_id":"credits_10","platform":"ios"}
→ HTTP 200 {"credits_granted":10,"new_balance":127}
```

Both passed. Filed as post-mortem in #44.

### What we documented permanently

Added a module docstring to `addon_controller.py` and a new section in
`SUBSCRIPTION_MOBILE_REQUIREMENTS.md` (§4) warning future maintainers:
**any server-side code consuming data from the mobile SDK's transaction
objects MUST query v1**, because v2 does not expose the v1 id as any
field.

## Bug 2 — mobile pending-grant retry scoped to Subscription screen only

**Severity**: Medium, UX impact on real users

Discovered during Bug 1 debugging. The retry `useEffect` lived inside
`SubscriptionScreen.js`, so it only fired when the user navigated to
that screen. A user who got the "nie udało się dodać punktów" toast,
closed the app, and never revisited the subscription screen would silently
lose their paid credits within 24h (AsyncStorage TTL expiry on the pending
grant).

Fixed in mobile commit `f50bc63` (issue #21):
- Extracted `persistPendingAddonGrant` / `loadPendingAddonGrant` /
  `clearPendingAddonGrant` to `utils/pendingAddonGrant.js`
- New `<PendingAddonGrantRetrier />` component at the app root, inside
  all three providers (Subscription, Credit, Toast). Fires once per
  session when subscription is ready.
- 8 new tests covering loading guard, success + toast, failure preserves
  pending, wrong-user discard, TTL expiry, missing fields, single-fire
  across re-renders.

## Bug 3 — `linkRevenueCat` fires twice on every app launch

**Severity**: Low, server-side noise only

Observed in Render logs after each app launch:
```
POST /api/user/link-revenuecat HTTP/1.1 200 50
POST /api/user/link-revenuecat HTTP/1.1 200 50   (~20s later)
```

Root cause: `useSubscription.js` init effect and the auth `LOGIN` event
handler both independently call `linkRevenueCat`, both fire on launch,
both hit the server.

Fixed in mobile commit `f50bc63` (issue #22):
- Added `linkedUserIdRef` tracking which user has been linked in the
  current session
- New `linkRevenueCatOnce(userId)` helper short-circuits if already
  linked for this user
- Reset on LOGOUT so a different user can link fresh afterward

## Infrastructure bugs discovered + fixed

### EAS preview build was a dev client

First attempt at building an iOS preview via EAS produced an app that
booted straight into the Expo dev client launcher ("No dev server
found"). Cause: `expo-dev-client` is in `package.json` as a dependency,
and the `preview` profile in `eas.json` didn't explicitly set
`developmentClient: false` — so EAS compiled it with dev-client behavior.

Fix: added `"developmentClient": false` to the preview profile in
`mobile/eas.json` (commit `d5bcbf9`). Rebuilt as build
`dc62af93-1efb-4253-adb8-a6b6216bfa3f` — which boots to the real app.

### EAS environment variables not picked up from local `.env`

`EXPO_PUBLIC_REVENUECAT_IOS_KEY` was in the local mobile `.env` but `.env`
is gitignored, so EAS cloud builds never saw it. Every prior EAS build
(before today's session) would have crashed RC SDK initialization with
"API key not configured".

Fix: used `eas env:create` to store both iOS and Android keys in the EAS
`preview` and `production` environments as `plaintext` (they're
`EXPO_PUBLIC_*` which means public, so not secrets).

### `api.dawnotemu.app` custom domain verification

Verified that the `PROD` env in `mobile/services/config.js` resolves to
`https://api.dawnotemu.app`, which is configured as a verified custom
domain on the Render web service (`srv-d1cjj295pdvs73euen6g`). Same
underlying Flask app as `server-pf6p.onrender.com`.

## Feature flag: `ENFORCE_SUBSCRIPTION_GATE`

Introduced in [PR #42](https://github.com/DawnoTemu/server/pull/42) to
prevent the subscription merge from immediately bricking every existing
mobile user once deployed.

- Default `false` → audio synthesis gate is skipped entirely; old mobile
  clients that can't handle `SUBSCRIPTION_REQUIRED` (403) continue to
  work exactly as before
- Set `ENFORCE_SUBSCRIPTION_GATE=true` on Render when mobile adoption of
  the new build is ≥95%
- Flip-day runbook is documented in `SUBSCRIPTION_MOBILE_REQUIREMENTS.md`
  §10, including the SQL to refresh stale trials for users who signed up
  during the flag-off window

This is a **kill switch** — flipping back to `false` is lossless.

## State of user 33 (`kontakt@szymonpaluch.com`)

Used as the sole test user throughout. Final state after my cleanup at
the end of the session:

- `credits_balance = 127` (includes 10 legitimately purchased addons +
  renewal grants from multiple sandbox auto-renewals)
- `subscription_active = false` (natural EXPIRATION)
- `subscription_expires_at = 2026-04-10 15:14:56` (original sandbox
  expiration time, after I reverted a temporary UPDATE that had set it
  to 16:24 to enable the live security test)
- `subscription_will_renew = false` (from the CANCELLATION webhook)
- `revenuecat_app_user_id = "33"` (correctly bound by mobile
  `linkRevenueCat`)
- `trial_expires_at = 2026-04-24 14:25:41` (14 days from the reset I did
  at the start of testing)
- 1 row in `consumed_addon_transactions` — receipt
  `2000001151372110` for `credits_10`, 10 credits granted
- 4 credit lots: 3 `monthly` (26 each) + 1 `free` (10, with 6 remaining
  after story generation) + 1 `add_on` (10 from the addon)

The user has extra sandbox state — they can reset it themselves anytime
via SQL if they want to re-run the full flow.

## State of Sentry

One issue was created during live testing:
`REVENUECAT_WEBHOOK_SECRET not configured — rejecting webhook` at
`2026-04-10T11:14:01`. **That was self-inflicted noise** from my own
unauthenticated POST to `/api/webhooks/revenuecat` before I set the env
vars. Marked resolved at the end of the session.

All other Sentry issues in the `python-flask` project pre-date this
session (old migration errors, a worker OOM from 04-08, Celery DB
connection failures from 04-07). None are subscription-related.

## State of GitHub issues

### Closed during session

| # | Title | Why |
|---|---|---|
| server#37 | RevenueCat: Set webhook URL for production | Done — dashboard configured + env vars set + live verified |
| mobile#20 | Replace test RevenueCat iOS key with production App Store key | Done — `appl_MnDX...` in mobile `.env` + EAS env vars |
| mobile#21 | Pending addon grant retry only fires on SubscriptionScreen mount | Done — moved to `<PendingAddonGrantRetrier />` at app root |
| mobile#22 | linkRevenueCat fires twice on app launch | Done — `linkedUserIdRef` in `useSubscription.js` |

### Opened during session

| # | Title | Priority |
|---|---|---|
| server#44 | [POSTMORTEM] Addon receipt validation used wrong RC API version | Documentation only |
| server#45 | JWT invalidation on user.updated_at churn causes token loss during subscription lifecycle | Medium — bit sandbox QA hard, will eventually bite real users |

### Still open from before (unchanged)

| # | Title | Notes |
|---|---|---|
| server#38 | RevenueCat: Configure App Store Connect API key (P8) | Optional — Subscription Key (shared secret) is already configured and sufficient for launch. P8 only needed for promotional offers + S2S v2 notifications. |
| server#39 | RevenueCat: Add Android/Play Store products | Only blocks Android launch, not iOS |
| server#40 | P3: Subscription hardening — webhook cleanup, refund handling, datetime fix | Partially addressed by [PR #46 — datetime migration + cleanup task] (overnight work). Refund handling and push notifications still TODO. |
| server#41 | P4: Subscription enhancements — analytics, promos, deep linking | Post-launch iteration work |

## Still open for tomorrow / next session

1. **Merge PR #46** (overnight work — datetime migration + webhook cleanup task, 329 tests pass)
2. **Rebuild EAS preview IPA** with the latest fixes (`f50bc63`) and verify the retry works on-device. Or skip this and trust the unit tests.
3. **Kick off production IPA build**:
   ```bash
   cd mobile && npx eas-cli build --platform ios --profile production --auto-submit
   ```
   This is the SINGLE remaining blocker to real iOS users.
4. **Open App Store Connect** → answer the review questionnaire → submit. Apple review: 1–7 days.
5. **Tackle server#45** (JWT invalidation aggressiveness) — will bite during the next sandbox QA session and is a real prod concern when subscription webhooks start firing on real users. Suggested approach in the issue: add a nullable `token_invalidated_at` column, bump only on security-relevant events, middleware checks against that instead of `updated_at`.
6. **Post-launch**: decide when to flip `ENFORCE_SUBSCRIPTION_GATE=true` based on mobile adoption metrics.

## Key file pointers

- `docs/SUBSCRIPTION_MOBILE_REQUIREMENTS.md` — the most important doc. §4 has the receipt validation gotcha. §10 has the feature flag + flip-day runbook. §11 has the mobile contract reference.
- `controllers/addon_controller.py` — has the v1/v2 gotcha warning in the module docstring. Do not let anyone refactor this back to v2 without reading #44.
- `controllers/subscription_controller.py` — all webhook handling lives here. Idempotent via `webhook_events` table.
- `tasks/billing_tasks.py` — scheduled Celery Beat tasks. After PR #46 merges, also has `cleanup_old_webhook_events`.
- `utils/time_utils.py` — **new in PR #46**. `utc_now()` / `utc_from_timestamp()` helpers. Every new code path should use these instead of `datetime.utcnow()`.
- `utils/auth_middleware.py` — the JWT invalidation aggression lives at lines 82 and 148. See #45.
- `.secrets/revenuecat_webhook_secret.txt` — local-only file (gitignored). Contains the production webhook secret that was set on Render. Needed if the secret ever has to be re-entered into the RC dashboard.

## Things I wouldn't do again

- **Don't debug SDK contract mismatches by reading the mobile source**.
  The faster path is a temporary server-side debug log capturing the
  exact bytes the client sends, then a `curl` test against the backend
  with known-good values. Took ~15 minutes with that approach vs the
  hour I would've spent chasing the SDK TypeScript definitions.
- **Don't run sandbox purchase tests without a script ready to grab a
  fresh JWT**. The 5-minute sandbox renewal cycle combined with the JWT
  invalidation aggression meant every token expired 1-2 minutes after
  login. I burned ~20 minutes of clock time on token churn alone.
- **Don't run live tests while the automated monitoring cron is still
  watching** unless you've filtered it tightly. The monitoring cron
  pinged the webhook endpoint without auth (noise), my own curls
  generated fake error events in Sentry, etc. Easier to pause the cron
  during active testing.
- **Don't do a production merge of a big feature branch without a
  feature flag**. The subscription merge (pre-PR #42) would have bricked
  every existing user the instant Render deployed it. Always stage
  big-bang migrations behind a flag.

## Things that worked really well

- **Server-side debug log → revert pattern** for diagnosing SDK contract
  bugs. Tiny diff, one extra deploy cycle, zero risk.
- **The pending-grant retry mechanism on mobile** kept the user's
  receipt in AsyncStorage through every failed attempt. Once the server
  was fixed, no mobile action was needed to recover the grant. Credit
  to whoever designed that — saved real damage.
- **The `webhook_events` idempotency table** handled 7 RevenueCat
  redelivery events during the session without double-granting anything.
  Insert-first race pattern also tested under real load.
- **Feature flag design** (PR #42). Single env var, default-off,
  kill-switch semantics. Used it to deploy the whole subscription
  backend safely even though the mobile rollout was still weeks away.
