# Server Requirements for Mobile Subscription Integration

This document specifies the server-side changes needed to support the mobile app's
RevenueCat subscription and trial user journey. The mobile app (merged in PR #13)
already calls these endpoints — they return 404 until implemented.

---

## 1. Trial System

### User Model Changes

Add to User model:

```python
trial_expires_at = db.Column(db.DateTime, nullable=True)
```

- Set on registration: `trial_expires_at = datetime.utcnow() + timedelta(days=TRIAL_DURATION_DAYS)`
- Nullable for legacy users (treat null as trial expired)
- `TRIAL_DURATION_DAYS` defaults to 14 (from env var)

### Helper Property

```python
@property
def trial_is_active(self):
    return self.trial_expires_at is not None and self.trial_expires_at > datetime.utcnow()
```

### Migration

```
flask db migrate -m "add trial_expires_at and subscription fields to users"
flask db upgrade
```

### Backfill

For existing users, set `trial_expires_at = created_at + timedelta(days=14)`. Users whose
computed trial has already expired will correctly show as expired.

---

## 2. Subscription Status Endpoint

### `GET /api/user/subscription-status`

**Auth:** JWT required (`@token_required`)

**Mobile client:** `services/subscriptionStatusService.js:16`

**Response (200):**

```json
{
  "trial": {
    "active": true,
    "expires_at": "2026-04-03T12:00:00Z",
    "days_remaining": 12
  },
  "subscription": {
    "active": false,
    "plan": null,
    "expires_at": null,
    "will_renew": false
  },
  "can_generate": true,
  "initial_credits": 10
}
```

**Required fields (mobile validates these):**
- `trial` (object) — must be present, not null
- `can_generate` (boolean) — must be present with `typeof === 'boolean'`

If either is missing, the mobile app treats the response as invalid and shows an error.

**Logic:**

```python
trial_active = user.trial_is_active
subscription_active = user.subscription_active  # from webhook data
can_generate = subscription_active or trial_active

days_remaining = max(0, (user.trial_expires_at - utcnow()).days) if user.trial_expires_at and trial_active else 0
```

**`initial_credits`** = `Config.INITIAL_CREDITS` (currently 10). The mobile app uses this
as a fallback display value; defaults to `DEFAULT_INITIAL_CREDITS = 10` if missing.

---

## 3. RevenueCat Webhook Endpoint

### `POST /api/webhooks/revenuecat`

**Auth:** Webhook authorization header validation (shared secret in `REVENUECAT_WEBHOOK_SECRET`)

RevenueCat sends webhook events when subscription state changes. The server must update
the user's subscription fields accordingly.

**Events to handle:**

| Event Type | Action |
|---|---|
| `INITIAL_PURCHASE` | Mark user as subscribed, grant credits based on plan (26 PM monthly / 30 PM annual) |
| `RENEWAL` | Grant credits based on plan |
| `CANCELLATION` | Set `subscription_will_renew = False` (keep active until period end) |
| `EXPIRATION` | Set `subscription_active = False` |
| `BILLING_ISSUE` | Log warning, optionally send push notification |
| `PRODUCT_CHANGE` | Update `subscription_plan` (future extensibility) |

**User lookup:** RevenueCat sends `app_user_id` which matches `revenuecat_app_user_id` on
the User model. The mobile app calls `Purchases.logIn(String(userId))` where `userId` is
the DawnoTemu integer user ID, so `revenuecat_app_user_id` will be a stringified integer.

**Security note — `/api/user/link-revenuecat` identity binding:** The server derives
`revenuecat_app_user_id` authoritatively from the authenticated `user.id` and does NOT
trust any client-supplied value. If the request body contains a
`revenuecat_app_user_id`, it must equal `str(user.id)` or the request is rejected with
`400`. This closes an account-hijack vector where a malicious client could pre-claim
another user's predictable RC id before the victim's first link call and block or
misroute their webhook events.

**Subscriber data to store on User model:**

```python
subscription_active = db.Column(db.Boolean, default=False)
subscription_plan = db.Column(db.String(50), nullable=True)      # 'monthly'
subscription_expires_at = db.Column(db.DateTime, nullable=True)
subscription_will_renew = db.Column(db.Boolean, default=False)
subscription_source = db.Column(db.String(20), nullable=True)     # 'app_store', 'play_store'
revenuecat_app_user_id = db.Column(db.String(100), nullable=True, index=True)
```

**Idempotency:** Webhook events may be delivered multiple times. Use the event's unique ID
or timestamp to prevent duplicate credit grants.

---

## 4. Add-on Credit Pack Grant Endpoint

### `POST /api/credits/grant-addon`

**Auth:** JWT required (`@token_required`)

**Mobile client:** `services/subscriptionStatusService.js:121`

**Request:**

```json
{
  "receipt_token": "rc_transaction_abc123",
  "product_id": "credits_10",
  "platform": "ios"
}
```

- `receipt_token` — RevenueCat `transactionIdentifier` (not an App Store/Play Store receipt).
  Used as the **idempotency key** to prevent double-grants.
- `product_id` — one of: `credits_10`, `credits_20`, `credits_30`
- `platform` — `"ios"` or `"android"`

**Success Response (200):**

```json
{
  "credits_granted": 10,
  "new_balance": 36
}
```

The mobile app validates that both `credits_granted` and `new_balance` are present and
numeric. If either is missing or non-numeric, the mobile treats the response as an error.

**Error Response (4xx/5xx):**

```json
{
  "error": "Human-readable error message"
}
```

**Logic:**

1. **Validate `receipt_token` uniqueness** — check against a `consumed_transactions` table
   (or equivalent). If already consumed, return `{ "credits_granted": <original_amount>, "new_balance": <current_balance> }` (idempotent success, not an error).
2. **Validate `product_id`** — must be a known product:
   - `credits_10` → 10 credits
   - `credits_20` → 20 credits
   - `credits_30` → 30 credits
3. **Validate subscription** — user must have `subscription_active = True`. Add-ons are
   subscriber-only. Return 403 if not subscribed.
4. **Validate receipt against RevenueCat v1 API AND verify product match** — look up the
   user's `non_subscriptions` via `/v1/subscribers/{app_user_id}` (not v2!), find the one
   matching `receipt_token` under `non_subscriptions[expected_product_id]`. If the receipt
   is not in the expected product's bucket, reject with 403. **Never trust the client's
   `product_id` alone** — without this check, a valid receipt for `credits_10` can be
   redeemed as `credits_30`, which is a billing bypass.

   > **Why v1 and not v2** (see [server#44](https://github.com/DawnoTemu/server/issues/44)): the mobile SDK
   > (`react-native-purchases` v9) exposes
   > `nonSubscriptionTransactions[i].transactionIdentifier` as the RevenueCat
   > **v1 internal id** (e.g. `o1_kSFvmriDAHzQ1wdJi0UAhg`). The v2 API does
   > NOT expose this id. If you query v2, matching always fails. Always use
   > v1 server-side when consuming data that originated from the mobile
   > SDK's transaction objects.
   >
   > v1 API uses platform-specific public keys (`REVENUECAT_IOS_PUBLIC_KEY`,
   > `REVENUECAT_ANDROID_PUBLIC_KEY`), not the v2 `sk_*` secret. Public keys
   > are safe to use server-side — they're designed to be embedded in
   > clients and have read-only scope for the specific app.
5. **Grant credits** — use existing `credit_model.grant()` with `source="add_on"`.
6. **Record transaction** — store `receipt_token`, `product_id`, `platform`, `user_id`,
   `credits_granted`, and `granted_at` to prevent replay.
7. **Return** `credits_granted` and `new_balance` (read from `user.credits_balance`
   after grant).

### Idempotency (Critical)

The mobile app has a **pending-grant retry mechanism**: if the grant call fails after a
successful purchase, the app persists the grant data to AsyncStorage and retries on next
launch (within 24 hours). This means the same `receipt_token` may be submitted multiple
times. The endpoint **must** be idempotent:

- If `receipt_token` was already consumed for this user, return 200 with the original
  `credits_granted` and current `new_balance`.
- If `receipt_token` was consumed for a different user, return 409 Conflict.

### Consumed Transactions Table

```python
class ConsumedAddonTransaction(db.Model):
    __tablename__ = 'consumed_addon_transactions'

    id = db.Column(db.Integer, primary_key=True)
    receipt_token = db.Column(db.String(255), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    product_id = db.Column(db.String(50), nullable=False)
    platform = db.Column(db.String(20), nullable=False)
    credits_granted = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

---

## 5. Generation Gate (Server-Side)

### Modify `audio_controller.synthesize_audio()`

Add a subscription/trial check **before** the existing credit check:

```python
def synthesize_audio(voice_id, story_id):
    user = get_current_user()

    # Check subscription OR trial
    if not user.subscription_active and not user.trial_is_active:
        return False, {"error": "Subscription required", "code": "SUBSCRIPTION_REQUIRED"}, 403

    # Existing credit check continues here...
```

Return **403** with code `SUBSCRIPTION_REQUIRED` (distinct from 402 `PAYMENT_REQUIRED`
for insufficient credits).

---

## 6. RevenueCat Configuration

### Products to Create

**Subscriptions (auto-renewable):**

| Product ID | Price | Credits | Period |
|---|---|---|---|
| `dawnotemu_monthly` | 39.99 PLN | 26 PM | monthly |
| `dawnotemu_annual` | 349 PLN | 30 PM/month (360/year, +15% bonus) | yearly |

**Consumables (add-on packs):**

| Product ID | Price | Credits |
|---|---|---|
| `credits_10` | 15.00 PLN | 10 PM |
| `credits_20` | 28.00 PLN | 20 PM |
| `credits_30` | 37.00 PLN | 30 PM |

### Entitlements

| Entitlement ID | Grants |
|---|---|
| `DawnoTemu Subscription` | Access to story generation |

The mobile app checks `customerInfo.entitlements.active['DawnoTemu Subscription']` to
determine subscription status (hardcoded in `services/subscriptionService.js:14`).

### Offerings

| Offering ID | Packages |
|---|---|
| `default` | `$rc_monthly` → `dawnotemu_monthly`, `$rc_annual` → `dawnotemu_annual` |
| `credit_packs` | `credits_10`, `credits_20`, `credits_30` |

The mobile app reads `offerings.current` for the subscription plan and
`offerings.all.credit_packs` for add-on packs.

---

## 7. Environment Variables (Server)

```bash
REVENUECAT_WEBHOOK_SECRET=<shared-secret>       # webhook auth
REVENUECAT_API_KEY=<revenuecat-v1-api-key>       # server-side API (optional, for receipt validation)
TRIAL_DURATION_DAYS=14                           # trial length for new users
MONTHLY_SUBSCRIPTION_CREDITS=26                  # credits granted per monthly renewal
ANNUAL_SUBSCRIPTION_CREDITS=30                   # credits granted per month on annual plan (+15% bonus)
```

Add to `config.py`:

```python
REVENUECAT_WEBHOOK_SECRET = os.getenv("REVENUECAT_WEBHOOK_SECRET")
REVENUECAT_API_KEY = os.getenv("REVENUECAT_API_KEY")
TRIAL_DURATION_DAYS = int(os.getenv("TRIAL_DURATION_DAYS", "14"))
MONTHLY_SUBSCRIPTION_CREDITS = int(os.getenv("MONTHLY_SUBSCRIPTION_CREDITS", "26"))
ANNUAL_SUBSCRIPTION_CREDITS = int(os.getenv("ANNUAL_SUBSCRIPTION_CREDITS", "30"))
```

---

## 8. Files to Create/Modify

### New Files

| File | Purpose |
|---|---|
| `routes/subscription_routes.py` | Blueprint with `GET /api/user/subscription-status` |
| `routes/webhook_routes.py` | Blueprint with `POST /api/webhooks/revenuecat` |
| `controllers/subscription_controller.py` | Subscription status logic, trial computation |
| `controllers/addon_controller.py` | Add-on credit grant logic with idempotency |
| `models/addon_transaction_model.py` | `ConsumedAddonTransaction` model |
| `tests/test_routes/test_subscription_routes.py` | Endpoint tests |
| `tests/test_controllers/test_subscription_controller.py` | Controller unit tests |
| `tests/test_controllers/test_addon_controller.py` | Addon grant tests |

### Modified Files

| File | Change |
|---|---|
| `models/user_model.py` | Add `trial_expires_at` + 5 subscription columns + `trial_is_active` property |
| `controllers/audio_controller.py` | Add subscription/trial gate before credit check |
| `routes/__init__.py` | Register new blueprints |
| `config.py` | Add RevenueCat + trial env vars |
| `routes/billing_routes.py` | Add `POST /api/credits/grant-addon` route |

---

## 9. Implementation Order

1. **Database migration** — add `trial_expires_at` + subscription fields + `consumed_addon_transactions` table
2. **`GET /api/user/subscription-status`** — mobile currently gets 404, this unblocks trial display
3. **`POST /api/credits/grant-addon`** — idempotent addon credit granting
4. **RevenueCat webhook** — receives subscription lifecycle events
5. **Generation gate** — add 403 `SUBSCRIPTION_REQUIRED` to `synthesize_audio`
6. **Backfill migration** — set `trial_expires_at = created_at + timedelta(days=14)` for existing users
7. **Tests** — full coverage for all new endpoints, controller logic, and edge cases

---

## 10. Subscription Gate Feature Flag (Rollout Safety)

The audio synthesis gate in `controllers/audio_controller.py` is controlled
by an environment variable so the server can be deployed with subscription
infrastructure live but enforcement disabled. This is necessary because the
mobile build without the subscription UI cannot handle a `403
SUBSCRIPTION_REQUIRED` response — old clients in the App Store / Play Store
would be bricked the moment the gate became active.

### The flag

```python
Config.ENFORCE_SUBSCRIPTION_GATE  # env: ENFORCE_SUBSCRIPTION_GATE
```

Default: `false` (gate bypassed).
Truthy values: `true`, `1`, `yes`, `on` (case-insensitive).

### What the flag controls

**Only one thing**: the subscription check in `AudioController.synthesize_audio()`.
When OFF, the gate block is skipped entirely — no user lookup, no
`can_generate` check, no 403 response. Old clients see identical behavior to
pre-subscription-merge.

### What the flag does NOT control

All of this remains fully functional regardless of the flag state:

- `GET /api/user/subscription-status` — still returns real trial/subscription state
- `POST /api/user/link-revenuecat` — still binds users to RevenueCat
- `POST /api/credits/grant-addon` — still grants add-on credits
- `POST /api/webhooks/revenuecat` — still processes lifecycle events
- Webhook credit grants (monthly / yearly subscribers)
- Scheduled billing tasks (`grant_yearly_subscriber_monthly_credits`, `expire_credit_lots`)
- `trial_expires_at` backfill on new signups
- Migration `b7e8f9a0c1d2` (schema + historical trial backfill)

The subscription state is always tracked correctly. The flag only affects
**enforcement** in the audio endpoint.

### Rollout plan

1. Deploy server with `ENFORCE_SUBSCRIPTION_GATE` unset or `false`
2. Old clients keep working; new clients on the updated build see the full
   subscription experience because they pre-check `can_generate` via the
   status endpoint and redirect to the paywall client-side
3. Monitor App Store Connect / Play Console adoption metrics
4. When ≥95% of daily-active users are on the new build, execute the
   flip-day runbook below

### Flip-day runbook

**Step 1 — Refresh stale trials.** Users who signed up during the flag-off
period had `trial_expires_at` set at registration, but the value is unused
while the flag is off. By flip time some of those trials are already past.
Run this SQL against the production database to give everyone without an
active subscription a fresh 14-day trial window:

```sql
UPDATE users
   SET trial_expires_at = NOW() + INTERVAL '14 days'
 WHERE subscription_active = FALSE
   AND revenuecat_app_user_id IS NULL;
```

Users who already subscribed keep their subscription. Users who linked
RevenueCat (including trial users on the new app) keep their existing
trial window.

**Step 2 — Flip the flag.** Set `ENFORCE_SUBSCRIPTION_GATE=true` on the
Render `dawnotemu-prod` env group. This triggers an auto-redeploy
(~2 minutes).

**Step 3 — Monitor.** Watch Sentry for `SUBSCRIPTION_REQUIRED` 403s and
check the customer support inbox for the next hour.

**Step 4 — Kill switch.** If anything breaks, set the flag back to `false`
and redeploy. The rollback is instant and lossless: no subscription state
is modified.

### Testing

The test suite defaults to `ENFORCE_SUBSCRIPTION_GATE = True` via a module-
level assignment in `tests/conftest.py` so all existing gate tests exercise
the fully-rolled-out behavior. Two dedicated tests in
`tests/test_controllers/test_audio_controller.py` use `monkeypatch` to cover
the flag-off path:

- `test_synthesize_audio_flag_off_allows_unsubscribed` — unsubscribed user
  with expired trial can still synthesize
- `test_synthesize_audio_flag_off_skips_user_lookup` — `UserModel.get_by_id`
  is never called (no new error paths leak through)

---

## 11. Mobile Contract Reference

The mobile app's expectations are defined in these files (source of truth):

- `services/subscriptionStatusService.js` — API client with exact URLs, request/response shapes, and validation
- `services/subscriptionService.js` — RevenueCat SDK wrapper, `ENTITLEMENT_ID = 'premium'`
- `services/config.js` — `DEFAULT_INITIAL_CREDITS = 10`, `DEFAULT_TRIAL_DAYS = 14`
- `screens/SubscriptionScreen.js` — `ADDON_PACKS_CONFIG` with product IDs and credit amounts
- `hooks/useSubscription.js` — state management, lapse detection, refresh logic
