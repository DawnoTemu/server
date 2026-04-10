"""Mobile ↔ Server integration tests.

Simulates the exact HTTP requests the React Native mobile app sends,
using the same endpoints, headers, payload shapes, and response
validation the mobile code performs.  Runs against a real Flask app
with a real database and — where possible — the live RevenueCat API.

Test structure mirrors the mobile user journey:
  1. Register & confirm email
  2. Login & get JWT
  3. Check subscription status (trial active)
  4. Link RevenueCat
  5. Trial expires → can_generate goes false
  6. Webhook: INITIAL_PURCHASE → subscription active
  7. Check credits balance
  8. Grant addon credits
  9. Webhook: CANCELLATION → will_renew false
 10. Webhook: EXPIRATION → can_generate false
"""

import json
import os
import time
from datetime import datetime, timedelta

import pytest

from config import Config
from database import db
from models.user_model import User, UserModel
from models.credit_model import get_user_credit_summary


# ---------------------------------------------------------------------------
# Helpers — mirror mobile request patterns
# ---------------------------------------------------------------------------

def _register(client, email, password):
    """POST /auth/register — same as mobile authService.register()."""
    return client.post(
        "/auth/register",
        data=json.dumps({
            "email": email,
            "password": password,
            "password_confirm": password,
        }),
        content_type="application/json",
    )


def _login(client, email, password):
    """POST /auth/login — same as mobile authService.login()."""
    return client.post(
        "/auth/login",
        data=json.dumps({"email": email, "password": password}),
        content_type="application/json",
    )


def _auth_headers(token):
    """Authorization header matching mobile: Bearer {token}."""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _get_subscription_status(client, token):
    """GET /api/user/subscription-status — same as subscriptionStatusService."""
    return client.get(
        "/api/user/subscription-status",
        headers=_auth_headers(token),
    )


def _link_revenuecat(client, token, rc_id):
    """POST /api/user/link-revenuecat — same as mobile."""
    return client.post(
        "/api/user/link-revenuecat",
        headers=_auth_headers(token),
        data=json.dumps({"revenuecat_app_user_id": rc_id}),
    )


def _get_credits(client, token):
    """GET /me/credits — same as mobile creditService.getCredits()."""
    return client.get("/me/credits", headers=_auth_headers(token))


def _get_story_credits(client, token, story_id):
    """GET /stories/{id}/credits — same as mobile creditService.getStoryCredits()."""
    return client.get(f"/stories/{story_id}/credits", headers=_auth_headers(token))


def _grant_addon(client, token, receipt_token, product_id, platform):
    """POST /api/credits/grant-addon — same as mobile grantAddonCredits()."""
    return client.post(
        "/api/credits/grant-addon",
        headers=_auth_headers(token),
        data=json.dumps({
            "receipt_token": receipt_token,
            "product_id": product_id,
            "platform": platform,
        }),
    )


def _send_webhook(client, event_type, app_user_id, event_id=None, **extra):
    """POST /api/webhooks/revenuecat — simulates RevenueCat webhook delivery."""
    secret = os.getenv("REVENUECAT_WEBHOOK_SECRET", "test-webhook-secret")
    evt = {
        "type": event_type,
        "id": event_id or f"evt_{event_type.lower()}_{int(time.time() * 1000)}",
        "app_user_id": app_user_id,
        "product_id": extra.pop("product_id", "monthly"),
        "store": extra.pop("store", "APP_STORE"),
        "expiration_at_ms": extra.pop(
            "expiration_at_ms",
            int((datetime.utcnow() + timedelta(days=35)).timestamp() * 1000),
        ),
    }
    evt.update(extra)
    return client.post(
        "/api/webhooks/revenuecat",
        headers={
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/json",
        },
        data=json.dumps({"event": evt}),
    )


def _prepare_user(app, email="mobile@test.com", password="SecurePass123!"):
    """Create a confirmed, active user with a JWT — simulates register + confirm + login."""
    with app.app_context():
        user = UserModel.create_user(email=email, password=password)
        user.email_confirmed = True
        db.session.commit()
        token = user._generate_token({"sub": user.id, "type": "access"}, 3600)
        return user.id, token


# ---------------------------------------------------------------------------
# Mobile response validation helpers (mirrors mobile JS parsing)
# ---------------------------------------------------------------------------

def _validate_subscription_status_shape(body):
    """Validates response matches what mobile subscriptionStatusService expects."""
    assert "trial" in body, f"Missing 'trial' key. Keys: {list(body.keys())}"
    assert "subscription" in body
    assert "can_generate" in body
    assert isinstance(body["can_generate"], bool)

    trial = body["trial"]
    assert "active" in trial
    assert "expires_at" in trial
    assert "days_remaining" in trial

    sub = body["subscription"]
    assert "active" in sub
    assert "plan" in sub
    assert "expires_at" in sub
    assert "will_renew" in sub


def _validate_credits_shape(body):
    """Validates response matches what mobile creditService expects."""
    assert "balance" in body
    assert "unit_label" in body
    assert "unit_size" in body
    assert isinstance(body["balance"], int)
    assert isinstance(body["unit_size"], int)


def _validate_addon_grant_shape(body):
    """Validates response matches what mobile grantAddonCredits expects."""
    assert "credits_granted" in body
    assert "new_balance" in body
    assert isinstance(body["credits_granted"], int)
    assert isinstance(body["new_balance"], int)


# ===========================================================================
# TEST SUITES
# ===========================================================================

class TestMobileRegistrationAndAuth:
    """Simulates the mobile registration → login flow."""

    def test_register_returns_success(self, app, client):
        resp = _register(client, "newuser@test.com", "SecurePass123!")
        assert resp.status_code in (200, 201), f"Registration failed: {resp.get_json()}"

    def test_login_after_registration(self, app, client):
        _register(client, "loginuser@test.com", "SecurePass123!")
        with app.app_context():
            user = User.query.filter_by(email="loginuser@test.com").first()
            user.email_confirmed = True
            user.is_active = True
            db.session.commit()

        resp = _login(client, "loginuser@test.com", "SecurePass123!")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "access_token" in body or "token" in body, f"No token in response: {list(body.keys())}"

    def test_unauthenticated_request_returns_401(self, client):
        resp = client.get("/api/user/subscription-status")
        assert resp.status_code in (401, 403)


class TestMobileSubscriptionStatus:
    """GET /api/user/subscription-status — exactly as mobile fetches it."""

    def test_new_user_has_active_trial(self, app, client):
        user_id, token = _prepare_user(app, "trial@test.com")
        resp = _get_subscription_status(client, token)
        assert resp.status_code == 200

        body = resp.get_json()
        _validate_subscription_status_shape(body)
        assert body["trial"]["active"] is True
        assert body["trial"]["days_remaining"] >= 13
        assert body["can_generate"] is True
        assert body["subscription"]["active"] is False

    def test_expired_trial_no_subscription(self, app, client):
        user_id, token = _prepare_user(app, "expired_trial@test.com")
        with app.app_context():
            user = db.session.get(User, user_id)
            user.trial_expires_at = datetime.utcnow() - timedelta(days=1)
            db.session.commit()

        resp = _get_subscription_status(client, token)
        assert resp.status_code == 200
        body = resp.get_json()
        _validate_subscription_status_shape(body)
        assert body["trial"]["active"] is False
        assert body["can_generate"] is False

    def test_active_subscription_shows_correctly(self, app, client):
        user_id, token = _prepare_user(app, "subscribed@test.com")
        with app.app_context():
            user = db.session.get(User, user_id)
            user.trial_expires_at = datetime.utcnow() - timedelta(days=1)
            user.subscription_active = True
            user.subscription_plan = "monthly"
            user.subscription_expires_at = datetime.utcnow() + timedelta(days=30)
            user.subscription_will_renew = True
            db.session.commit()

        resp = _get_subscription_status(client, token)
        body = resp.get_json()
        assert body["subscription"]["active"] is True
        assert body["subscription"]["plan"] == "monthly"
        assert body["subscription"]["will_renew"] is True
        assert body["can_generate"] is True
        assert body["subscription"]["expires_at"] is not None


class TestMobileLinkRevenueCat:
    """POST /api/user/link-revenuecat — linking mobile user to RevenueCat.

    Mobile calls Purchases.logIn(String(userId)) and then posts the same id
    to this endpoint. The server derives the RC id authoritatively from the
    authenticated user.id, so any other value is rejected.
    """

    def test_link_success_with_matching_id(self, app, client):
        user_id, token = _prepare_user(app, "link@test.com")
        resp = _link_revenuecat(client, token, str(user_id))
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["revenuecat_app_user_id"] == str(user_id)

    def test_link_empty_body_succeeds(self, app, client):
        user_id, token = _prepare_user(app, "link_empty@test.com")
        resp = _link_revenuecat(client, token, "  ")
        assert resp.status_code == 200
        assert resp.get_json()["revenuecat_app_user_id"] == str(user_id)

    def test_link_rejects_hijack_attempt(self, app, client):
        """SECURITY: user A cannot claim user B's predictable RC id."""
        user_a_id, token_a = _prepare_user(app, "link_a@test.com")
        user_b_id, _token_b = _prepare_user(app, "link_b@test.com")

        # User A tries to claim user B's id
        resp = _link_revenuecat(client, token_a, str(user_b_id))
        assert resp.status_code == 400

        # User A's RC id was NOT set to user B's id
        with app.app_context():
            user_a = db.session.get(User, user_a_id)
            assert user_a.revenuecat_app_user_id != str(user_b_id)


class TestMobileCredits:
    """GET /me/credits — mobile creditService.getCredits()."""

    def test_new_user_has_initial_credits(self, app, client):
        user_id, token = _prepare_user(app, "credits@test.com")
        resp = _get_credits(client, token)
        assert resp.status_code == 200
        body = resp.get_json()
        _validate_credits_shape(body)
        assert body["balance"] >= 0
        assert body["unit_label"] is not None

    def test_credits_after_subscription_grant(self, app, client):
        user_id, token = _prepare_user(app, "credits_sub@test.com")

        with app.app_context():
            user = db.session.get(User, user_id)
            user.revenuecat_app_user_id = "rc_credits_sub"
            db.session.commit()
            balance_before = user.credits_balance

        # Simulate webhook granting credits
        _send_webhook(client, "INITIAL_PURCHASE", "rc_credits_sub")

        resp = _get_credits(client, token)
        body = resp.get_json()
        assert body["balance"] > balance_before


class TestMobileStoryCredits:
    """GET /stories/{id}/credits — mobile creditService.getStoryCredits()."""

    def test_story_credits_returns_required(self, app, client):
        user_id, token = _prepare_user(app, "story_credits@test.com")
        with app.app_context():
            from models.story_model import Story
            story = Story(
                title="Test Story", author="Author",
                content="A" * 2000,  # 2000 chars = 2 credits at 1000 chars/credit
            )
            db.session.add(story)
            db.session.commit()
            story_id = story.id

        resp = _get_story_credits(client, token, story_id)
        assert resp.status_code == 200
        body = resp.get_json()
        assert "required_credits" in body
        assert isinstance(body["required_credits"], int)
        assert body["required_credits"] >= 1

    def test_nonexistent_story_returns_404(self, app, client):
        user_id, token = _prepare_user(app, "story_404@test.com")
        resp = _get_story_credits(client, token, 99999)
        assert resp.status_code == 404


class TestMobileWebhookFlow:
    """Simulates RevenueCat → server webhook → mobile polls status."""

    def test_initial_purchase_webhook_updates_status(self, app, client):
        user_id, token = _prepare_user(app, "wh_purchase@test.com")
        with app.app_context():
            user = db.session.get(User, user_id)
            user.revenuecat_app_user_id = "rc_wh_purchase"
            user.trial_expires_at = datetime.utcnow() - timedelta(days=1)
            db.session.commit()

        # Before: can_generate is False
        resp = _get_subscription_status(client, token)
        assert resp.get_json()["can_generate"] is False

        # Webhook arrives
        wh_resp = _send_webhook(client, "INITIAL_PURCHASE", "rc_wh_purchase")
        assert wh_resp.status_code == 200

        # After: mobile polls and sees active subscription
        resp = _get_subscription_status(client, token)
        body = resp.get_json()
        assert body["subscription"]["active"] is True
        assert body["can_generate"] is True

    def test_cancellation_webhook_updates_will_renew(self, app, client):
        user_id, token = _prepare_user(app, "wh_cancel@test.com")
        with app.app_context():
            user = db.session.get(User, user_id)
            user.revenuecat_app_user_id = "rc_wh_cancel"
            user.subscription_active = True
            user.subscription_will_renew = True
            user.subscription_expires_at = datetime.utcnow() + timedelta(days=20)
            db.session.commit()

        _send_webhook(client, "CANCELLATION", "rc_wh_cancel")

        resp = _get_subscription_status(client, token)
        body = resp.get_json()
        # Subscription still active, but won't renew
        assert body["subscription"]["active"] is True
        assert body["subscription"]["will_renew"] is False

    def test_expiration_webhook_blocks_generation(self, app, client):
        user_id, token = _prepare_user(app, "wh_expire@test.com")
        with app.app_context():
            user = db.session.get(User, user_id)
            user.revenuecat_app_user_id = "rc_wh_expire"
            user.trial_expires_at = datetime.utcnow() - timedelta(days=30)
            user.subscription_active = True
            user.subscription_will_renew = False
            user.subscription_expires_at = datetime.utcnow() - timedelta(hours=1)
            db.session.commit()

        _send_webhook(client, "EXPIRATION", "rc_wh_expire")

        resp = _get_subscription_status(client, token)
        body = resp.get_json()
        assert body["subscription"]["active"] is False
        assert body["can_generate"] is False

    def test_renewal_webhook_extends_expiry(self, app, client):
        user_id, token = _prepare_user(app, "wh_renew@test.com")
        with app.app_context():
            user = db.session.get(User, user_id)
            user.revenuecat_app_user_id = "rc_wh_renew"
            user.subscription_active = True
            user.subscription_expires_at = datetime.utcnow() + timedelta(days=2)
            db.session.commit()

        new_expiry = int((datetime.utcnow() + timedelta(days=35)).timestamp() * 1000)
        _send_webhook(client, "RENEWAL", "rc_wh_renew", expiration_at_ms=new_expiry)

        resp = _get_subscription_status(client, token)
        body = resp.get_json()
        assert body["subscription"]["active"] is True
        assert body["subscription"]["will_renew"] is True

    def test_billing_issue_webhook(self, app, client):
        user_id, token = _prepare_user(app, "wh_billing@test.com")
        with app.app_context():
            user = db.session.get(User, user_id)
            user.revenuecat_app_user_id = "rc_wh_billing"
            user.subscription_active = True
            user.subscription_expires_at = datetime.utcnow() + timedelta(days=20)
            db.session.commit()

        wh_resp = _send_webhook(client, "BILLING_ISSUE", "rc_wh_billing")
        assert wh_resp.status_code == 200

        with app.app_context():
            user = db.session.get(User, user_id)
            assert user.billing_issue_at is not None

    def test_product_change_webhook(self, app, client):
        user_id, token = _prepare_user(app, "wh_change@test.com")
        with app.app_context():
            user = db.session.get(User, user_id)
            user.revenuecat_app_user_id = "rc_wh_change"
            user.subscription_active = True
            user.subscription_plan = "monthly"
            user.subscription_expires_at = datetime.utcnow() + timedelta(days=20)
            db.session.commit()

        _send_webhook(
            client, "PRODUCT_CHANGE", "rc_wh_change",
            new_product_id="yearly",
        )

        resp = _get_subscription_status(client, token)
        body = resp.get_json()
        assert body["subscription"]["plan"] == "yearly"

    def test_duplicate_webhook_is_idempotent(self, app, client):
        user_id, _ = _prepare_user(app, "wh_dedup@test.com")
        with app.app_context():
            user = db.session.get(User, user_id)
            user.revenuecat_app_user_id = "rc_wh_dedup"
            db.session.commit()

        evt_id = "evt_dedup_mobile_test"
        r1 = _send_webhook(client, "INITIAL_PURCHASE", "rc_wh_dedup", event_id=evt_id)
        r2 = _send_webhook(client, "INITIAL_PURCHASE", "rc_wh_dedup", event_id=evt_id)
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r2.get_json()["status"] == "already_processed"


class TestMobileWebhookAuth:
    """Webhook auth — matches how RevenueCat sends the Authorization header."""

    def test_no_auth_rejected(self, client):
        resp = client.post(
            "/api/webhooks/revenuecat",
            data=json.dumps({"event": {"type": "TEST", "id": "no_auth"}}),
            content_type="application/json",
        )
        assert resp.status_code == 401

    def test_wrong_secret_rejected(self, client):
        resp = client.post(
            "/api/webhooks/revenuecat",
            headers={"Authorization": "Bearer wrong_secret"},
            data=json.dumps({"event": {"type": "TEST", "id": "bad_auth"}}),
            content_type="application/json",
        )
        assert resp.status_code == 401

    def test_bearer_prefix_accepted(self, client):
        secret = os.getenv("REVENUECAT_WEBHOOK_SECRET", "test-webhook-secret")
        resp = client.post(
            "/api/webhooks/revenuecat",
            headers={"Authorization": f"Bearer {secret}"},
            data=json.dumps({"event": {"type": "TEST", "id": "bearer_ok"}}),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_raw_secret_accepted(self, client):
        """RevenueCat may send secret without Bearer prefix."""
        secret = os.getenv("REVENUECAT_WEBHOOK_SECRET", "test-webhook-secret")
        resp = client.post(
            "/api/webhooks/revenuecat",
            headers={"Authorization": secret},
            data=json.dumps({"event": {"type": "TEST", "id": "raw_ok"}}),
            content_type="application/json",
        )
        assert resp.status_code == 200


class TestMobileAddonGrant:
    """POST /api/credits/grant-addon — same as mobile grantAddonCredits()."""

    def _subscribed_user(self, app, email):
        user_id, token = _prepare_user(app, email)
        with app.app_context():
            user = db.session.get(User, user_id)
            user.subscription_active = True
            user.subscription_expires_at = datetime.utcnow() + timedelta(days=30)
            user.revenuecat_app_user_id = f"rc_{email.split('@')[0]}"
            db.session.commit()
        return user_id, token

    def test_grant_success(self, app, client):
        from unittest.mock import patch
        user_id, token = self._subscribed_user(app, "addon_ok@test.com")

        with patch("controllers.addon_controller._validate_receipt_with_revenuecat", return_value=True):
            resp = _grant_addon(client, token, "txn_mobile_001", "credits_10", "ios")

        assert resp.status_code == 200
        body = resp.get_json()
        _validate_addon_grant_shape(body)
        assert body["credits_granted"] == 10

    def test_grant_idempotent_replay(self, app, client):
        """Mobile retry safety net — same receipt returns same result."""
        from unittest.mock import patch
        user_id, token = self._subscribed_user(app, "addon_idem@test.com")

        with patch("controllers.addon_controller._validate_receipt_with_revenuecat", return_value=True):
            r1 = _grant_addon(client, token, "txn_idem_001", "credits_10", "ios")
            r2 = _grant_addon(client, token, "txn_idem_001", "credits_10", "ios")

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.get_json()["credits_granted"] == r2.get_json()["credits_granted"]

    def test_unknown_product_rejected(self, app, client):
        user_id, token = self._subscribed_user(app, "addon_bad@test.com")
        resp = _grant_addon(client, token, "txn_bad", "credits_999", "ios")
        assert resp.status_code == 400

    def test_invalid_platform_rejected(self, app, client):
        user_id, token = self._subscribed_user(app, "addon_plat@test.com")
        resp = _grant_addon(client, token, "txn_plat", "credits_10", "web")
        assert resp.status_code == 400

    def test_no_subscription_rejected(self, app, client):
        user_id, token = _prepare_user(app, "addon_nosub@test.com")
        with app.app_context():
            user = db.session.get(User, user_id)
            user.trial_expires_at = datetime.utcnow() - timedelta(days=1)
            db.session.commit()

        resp = _grant_addon(client, token, "txn_nosub", "credits_10", "ios")
        assert resp.status_code == 403

    def test_missing_fields_rejected(self, app, client):
        user_id, token = self._subscribed_user(app, "addon_miss@test.com")
        resp = client.post(
            "/api/credits/grant-addon",
            headers=_auth_headers(token),
            data=json.dumps({"receipt_token": "txn_123"}),  # missing product_id, platform
        )
        assert resp.status_code == 400


class TestMobileFullJourney:
    """End-to-end: simulates a complete mobile user journey."""

    def test_trial_to_subscribe_to_addon_to_expire(self, app, client):
        from unittest.mock import patch

        # Step 1: New user with trial
        user_id, token = _prepare_user(app, "journey@mobile.com")

        resp = _get_subscription_status(client, token)
        body = resp.get_json()
        assert body["trial"]["active"] is True
        assert body["can_generate"] is True

        # Step 2: Link RevenueCat (mobile does this after SDK login)
        # Server derives RC id from user.id authoritatively
        resp = _link_revenuecat(client, token, str(user_id))
        assert resp.status_code == 200
        rc_id = str(user_id)

        # Step 3: Check initial credits
        resp = _get_credits(client, token)
        initial_balance = resp.get_json()["balance"]

        # Step 4: Trial expires
        with app.app_context():
            user = db.session.get(User, user_id)
            user.trial_expires_at = datetime.utcnow() - timedelta(days=1)
            db.session.commit()

        resp = _get_subscription_status(client, token)
        assert resp.get_json()["can_generate"] is False

        # Step 5: User subscribes (webhook from RevenueCat)
        wh_resp = _send_webhook(client, "INITIAL_PURCHASE", rc_id)
        assert wh_resp.status_code == 200

        # Step 6: Mobile polls — subscription active
        resp = _get_subscription_status(client, token)
        body = resp.get_json()
        assert body["subscription"]["active"] is True
        assert body["can_generate"] is True

        # Step 7: Credits increased from subscription grant
        resp = _get_credits(client, token)
        assert resp.get_json()["balance"] > initial_balance

        # Step 8: User buys addon credits
        with patch("controllers.addon_controller._validate_receipt_with_revenuecat", return_value=True):
            resp = _grant_addon(client, token, "txn_journey_addon", "credits_20", "ios")
        assert resp.status_code == 200
        body = resp.get_json()
        _validate_addon_grant_shape(body)
        assert body["credits_granted"] == 20

        # Step 9: Verify balance after addon
        resp = _get_credits(client, token)
        balance_after_addon = resp.get_json()["balance"]
        assert balance_after_addon > initial_balance

        # Step 10: User cancels (still active until period ends)
        _send_webhook(client, "CANCELLATION", rc_id)
        resp = _get_subscription_status(client, token)
        body = resp.get_json()
        assert body["subscription"]["active"] is True
        assert body["subscription"]["will_renew"] is False
        assert body["can_generate"] is True

        # Step 11: Subscription expires
        _send_webhook(client, "EXPIRATION", rc_id)
        resp = _get_subscription_status(client, token)
        body = resp.get_json()
        assert body["subscription"]["active"] is False
        assert body["can_generate"] is False


class TestMobileResponseContractValidation:
    """Validates that server responses match the exact shapes mobile JS code parses."""

    def test_subscription_status_has_initial_credits(self, app, client):
        """Mobile reads body.initial_credits with fallback to DEFAULT_INITIAL_CREDITS."""
        user_id, token = _prepare_user(app, "contract_init@test.com")
        resp = _get_subscription_status(client, token)
        body = resp.get_json()
        assert "initial_credits" in body
        assert isinstance(body["initial_credits"], int)
        assert body["initial_credits"] > 0

    def test_subscription_status_dates_are_iso_or_null(self, app, client):
        """Mobile parses expires_at with new Date() — must be ISO-8601 or null."""
        user_id, token = _prepare_user(app, "contract_dates@test.com")
        resp = _get_subscription_status(client, token)
        body = resp.get_json()

        trial_expires = body["trial"]["expires_at"]
        if trial_expires is not None:
            # Should be parseable as ISO datetime
            assert "T" in trial_expires, f"Not ISO format: {trial_expires}"

        sub_expires = body["subscription"]["expires_at"]
        # null is acceptable for no subscription
        assert sub_expires is None or "T" in sub_expires

    def test_credits_response_has_lots_and_transactions(self, app, client):
        """Mobile normalizes lots and recent_transactions arrays."""
        user_id, token = _prepare_user(app, "contract_credits@test.com")
        resp = _get_credits(client, token)
        body = resp.get_json()
        _validate_credits_shape(body)
        assert "lots" in body
        assert isinstance(body["lots"], list)
        assert "recent_transactions" in body
        assert isinstance(body["recent_transactions"], list)

    def test_addon_grant_error_has_error_field(self, app, client):
        """Mobile reads body.error on failure responses."""
        user_id, token = _prepare_user(app, "contract_err@test.com")
        resp = _grant_addon(client, token, "txn_err", "credits_999", "ios")
        assert resp.status_code == 400
        body = resp.get_json()
        assert "error" in body
        assert isinstance(body["error"], str)
