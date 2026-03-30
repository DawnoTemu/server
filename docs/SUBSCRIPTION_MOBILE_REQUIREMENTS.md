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
4. **Grant credits** — use existing `credit_model.grant()` with `source="add_on"`.
5. **Record transaction** — store `receipt_token`, `product_id`, `platform`, `user_id`,
   `credits_granted`, and `granted_at` to prevent replay.
6. **Return** `credits_granted` and `new_balance` (read from `user.credits_balance`
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

## 10. Mobile Contract Reference

The mobile app's expectations are defined in these files (source of truth):

- `services/subscriptionStatusService.js` — API client with exact URLs, request/response shapes, and validation
- `services/subscriptionService.js` — RevenueCat SDK wrapper, `ENTITLEMENT_ID = 'premium'`
- `services/config.js` — `DEFAULT_INITIAL_CREDITS = 10`, `DEFAULT_TRIAL_DAYS = 14`
- `screens/SubscriptionScreen.js` — `ADDON_PACKS_CONFIG` with product IDs and credit amounts
- `hooks/useSubscription.js` — state management, lapse detection, refresh logic
