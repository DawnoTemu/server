# Goal
Introduce paid subscriptions using Stripe while reusing the existing credit ledger. Keep mobile integration simple and low-cost by using Stripe-hosted Checkout and Customer Portal, opened in the system browser with deep links back into the app.

## Architecture Decision
- Credits remain the billing currency; subscriptions grant monthly credit lots (`source="monthly"`, `expires_at=current_period_end`).
- Use Stripe Checkout (mode=subscription) and Stripe Customer Portal; no custom card UI or in-app PCI scope.
- Webhooks drive state: invoice success → grant credits + mark active; subscription update/cancel → update status; invoice failure → mark past_due.
- Limit code surface to server-side: new subscription fields on `User`, new billing endpoints, webhook handler, and lightweight mobile redirects.

## Backend Implementation Plan
1) Data model: add `stripe_customer_id`, `stripe_subscription_id`, `subscription_status`, `subscription_started_at`, `subscription_current_period_end`, `plan_id`, `plan_credits_per_period` on `User` (or a small `subscriptions` table). Migration + Config defaults.  
2) Config/env: add `STRIPE_API_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_BASIC` (and any other prices), `STRIPE_SUCCESS_URL`, `STRIPE_CANCEL_URL`, optional `STRIPE_PORTAL_RETURN_URL`; fail fast if missing.  
3) Endpoints (billing blueprint):  
   - `POST /billing/checkout-session` (Bearer): create/reuse Stripe customer, create subscription Checkout session for configured price, include `metadata.user_id` and `client_reference_id`, return `checkout_url`.  
   - `POST /billing/portal-session` (Bearer): create Customer Portal session for current user; return `portal_url`.  
   - `POST /billing/stripe/webhook` (unauth): verify signature, handle events below.  
4) Webhook handling:  
   - `checkout.session.completed`: persist `stripe_customer_id`/`stripe_subscription_id`, set status=active, store period end.  
   - `invoice.payment_succeeded`: grant credits via `credit_model.grant(user_id, amount=plan_credits_per_period, source="monthly", reason="subscription_invoice", expires_at=current_period_end)`; update period end/status.  
   - `customer.subscription.updated/deleted` + `invoice.payment_failed`: update status to past_due/canceled and stop grants.  
5) Scheduler alignment: disable or guard `tasks/billing_tasks.grant_monthly_credits` (only run when `MONTHLY_CREDITS_DEFAULT>0` and no Stripe sub). Keep `expire_credit_lots` for period expirations.  
6) Docs/OpenAPI: document new User fields, endpoints, webhook contract, and mobile redirect flow.  
7) Tests: mock Stripe to cover checkout creation, portal creation, and webhook flows (invoice success, payment failed, cancel). Assert credit grants and subscription flags change; ensure debit/refund paths unchanged.

## Mobile Frontend Changes (minimal)
- “Subscribe” CTA → call `POST /billing/checkout-session`, open `checkout_url` in system browser/SFSafari/Custom Tab.  
- Configure universal link/custom scheme for `STRIPE_SUCCESS_URL` and `STRIPE_CANCEL_URL` so Stripe redirect returns to the app; on return, show “processing” and poll `/me/credits` or `/auth/me` until `subscription_status` is `active` and credits appear.  
- “Manage subscription” → call `POST /billing/portal-session`, open `portal_url`.  
- Handle cancel/error redirects gracefully with a retry CTA; no embedded card UI or Stripe SDK required.  
- Optional: add a lightweight “Refresh status” button if deep link fails and user returns manually.

## Stripe Account Setup Guide
1) Create Stripe account (start in test mode).  
2) Products/Prices: create recurring Product; copy Price ID to `STRIPE_PRICE_BASIC` (and any other tiers). Set interval/amount.  
3) API keys: set secret key as `STRIPE_API_KEY` (server-side only).  
4) Webhooks: add endpoint to `/billing/stripe/webhook`; subscribe to `checkout.session.completed`, `invoice.payment_succeeded`, `invoice.payment_failed`, `customer.subscription.updated`, `customer.subscription.deleted`. Store signing secret as `STRIPE_WEBHOOK_SECRET`.  
5) Success/Cancel URLs: set `STRIPE_SUCCESS_URL`/`STRIPE_CANCEL_URL` to universal links or HTTPS pages that hand control back to the app.  
6) Customer Portal: enable in Dashboard; allow cancel/plan-change/payment-method updates; set return URL → `STRIPE_PORTAL_RETURN_URL`.  
7) Go-live: swap to live keys and live price IDs, add live webhook endpoint, rotate env vars, and verify live webhooks before enabling in the mobile app.

## Risks & Mitigations
- Store policy risk (App Store/Play Store may require native IAP); confirm distribution and compliance early.  
- Webhook delivery drift; keep handlers idempotent (keyed by invoice/sub IDs) and log failures.  
- Period alignment; always use Stripe `current_period_end` for lot `expires_at` to match billing cycles.  
- Redirect failures; ensure success/cancel URLs resolve and provide manual “refresh status” in UI.

## Validation
- Automated: tests for checkout/portal creation and webhook flows (mocked Stripe); regression on credit debit/refund paths.  
- Manual: run test-mode checkout, observe webhook grant updating `/me/credits`; cancel in portal and see status change; verify mobile redirect back to app via universal link.***
