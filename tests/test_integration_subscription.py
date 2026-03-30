"""Integration tests for subscription system.

These tests exercise real controller logic, real DB writes, and real HTTP
endpoints via the Flask test client — no mocking of business logic.
"""

import json
import time
from datetime import datetime, timedelta

import pytest

from database import db
from models.user_model import User, UserModel
from models.webhook_event_model import WebhookEvent
from models.addon_transaction_model import ConsumedAddonTransaction
from models.credit_model import get_user_credit_summary
from controllers.subscription_controller import SubscriptionController
from controllers.addon_controller import AddonController


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_user(email="test@example.com", password="securepass123"):
    user = UserModel.create_user(email=email, password=password)
    db.session.refresh(user)
    return user


def _auth_header(app, user):
    """Generate a valid JWT for the given user, ensuring auth middleware passes."""
    # Auth middleware requires email_confirmed=True and is_active=True
    if not user.email_confirmed:
        user.email_confirmed = True
        db.session.commit()
    token = user._generate_token({"sub": user.id, "type": "access"}, 3600)
    return {"Authorization": f"Bearer {token}"}


def _webhook_payload(event_type, app_user_id, event_id=None, **extra):
    evt = {
        "type": event_type,
        "id": event_id or f"evt_{event_type.lower()}_{int(time.time()*1000)}",
        "app_user_id": app_user_id,
        "product_id": "dawnotemu_monthly",
        "store": "APP_STORE",
        "expiration_at_ms": int((datetime.utcnow() + timedelta(days=35)).timestamp() * 1000),
    }
    evt.update(extra)
    return {"event": evt}


# ---------------------------------------------------------------------------
# 1. User model: trial and subscription properties
# ---------------------------------------------------------------------------

class TestUserTrialAndSubscription:

    def test_new_user_has_active_trial(self, app):
        with app.app_context():
            user = _create_user()
            assert user.trial_is_active is True
            assert user.can_generate is True
            assert user.subscription_is_active is False

    def test_expired_trial_blocks_generation(self, app):
        with app.app_context():
            user = _create_user()
            user.trial_expires_at = datetime.utcnow() - timedelta(days=1)
            db.session.commit()
            db.session.refresh(user)
            assert user.trial_is_active is False
            assert user.can_generate is False

    def test_subscription_enables_generation_after_trial(self, app):
        with app.app_context():
            user = _create_user()
            # Expire trial
            user.trial_expires_at = datetime.utcnow() - timedelta(days=1)
            # Activate subscription
            user.subscription_active = True
            user.subscription_expires_at = datetime.utcnow() + timedelta(days=30)
            db.session.commit()
            db.session.refresh(user)
            assert user.trial_is_active is False
            assert user.subscription_is_active is True
            assert user.can_generate is True

    def test_subscription_without_expiry_is_inactive(self, app):
        with app.app_context():
            user = _create_user()
            user.subscription_active = True
            user.subscription_expires_at = None
            db.session.commit()
            db.session.refresh(user)
            assert user.subscription_is_active is False

    def test_expired_subscription_is_inactive(self, app):
        with app.app_context():
            user = _create_user()
            user.subscription_active = True
            user.subscription_expires_at = datetime.utcnow() - timedelta(hours=1)
            db.session.commit()
            db.session.refresh(user)
            assert user.subscription_is_active is False

    def test_to_dict_includes_subscription_fields(self, app):
        with app.app_context():
            user = _create_user()
            d = user.to_dict()
            assert "trial_is_active" in d
            assert "subscription_is_active" in d
            assert "can_generate" in d
            assert "subscription_plan" in d
            assert "subscription_will_renew" in d


# ---------------------------------------------------------------------------
# 2. SubscriptionController — get_subscription_status
# ---------------------------------------------------------------------------

class TestGetSubscriptionStatus:

    def test_returns_trial_info(self, app):
        with app.app_context():
            user = _create_user()
            ok, data, status = SubscriptionController.get_subscription_status(user)
            assert ok is True
            assert status == 200
            assert data["trial"]["active"] is True
            assert data["trial"]["days_remaining"] >= 13
            assert data["can_generate"] is True

    def test_shows_subscription_when_active(self, app):
        with app.app_context():
            user = _create_user()
            user.trial_expires_at = datetime.utcnow() - timedelta(days=1)
            user.subscription_active = True
            user.subscription_plan = "dawnotemu_monthly"
            user.subscription_expires_at = datetime.utcnow() + timedelta(days=30)
            user.subscription_will_renew = True
            db.session.commit()
            db.session.refresh(user)

            ok, data, status = SubscriptionController.get_subscription_status(user)
            assert data["subscription"]["active"] is True
            assert data["subscription"]["plan"] == "dawnotemu_monthly"
            assert data["subscription"]["will_renew"] is True
            assert data["can_generate"] is True


# ---------------------------------------------------------------------------
# 3. SubscriptionController — link_revenuecat
# ---------------------------------------------------------------------------

class TestLinkRevenueCat:

    def test_link_success(self, app):
        with app.app_context():
            user = _create_user()
            ok, data, status = SubscriptionController.link_revenuecat(user, "rc_user_123")
            assert ok is True
            assert status == 200
            assert data["revenuecat_app_user_id"] == "rc_user_123"
            db.session.refresh(user)
            assert user.revenuecat_app_user_id == "rc_user_123"

    def test_link_empty_id_rejected(self, app):
        with app.app_context():
            user = _create_user()
            ok, data, status = SubscriptionController.link_revenuecat(user, "  ")
            assert ok is False
            assert status == 400

    def test_link_too_long_rejected(self, app):
        with app.app_context():
            user = _create_user()
            ok, data, status = SubscriptionController.link_revenuecat(user, "x" * 101)
            assert ok is False
            assert status == 400

    def test_link_conflict_with_other_user(self, app):
        with app.app_context():
            user1 = _create_user("a@test.com")
            user2 = _create_user("b@test.com")
            SubscriptionController.link_revenuecat(user1, "shared_id")
            ok, data, status = SubscriptionController.link_revenuecat(user2, "shared_id")
            assert ok is False
            assert status == 409


# ---------------------------------------------------------------------------
# 4. Webhook handling — full lifecycle
# ---------------------------------------------------------------------------

class TestWebhookLifecycle:

    def test_test_event_returns_ok(self, app):
        with app.app_context():
            payload = {"event": {"type": "TEST", "id": "test_evt_1"}}
            ok, data, status = SubscriptionController.handle_revenuecat_webhook(payload)
            assert ok is True
            assert status == 200

    def test_missing_event_returns_400(self, app):
        with app.app_context():
            ok, data, status = SubscriptionController.handle_revenuecat_webhook({})
            assert ok is False
            assert status == 400

    def test_unknown_user_returns_404(self, app):
        with app.app_context():
            payload = _webhook_payload("INITIAL_PURCHASE", "nonexistent_user")
            ok, data, status = SubscriptionController.handle_revenuecat_webhook(payload)
            assert ok is False
            assert status == 404

    def test_initial_purchase_activates_subscription(self, app):
        with app.app_context():
            user = _create_user()
            user.revenuecat_app_user_id = "rc_1"
            db.session.commit()

            payload = _webhook_payload("INITIAL_PURCHASE", "rc_1")
            ok, data, status = SubscriptionController.handle_revenuecat_webhook(payload)
            assert ok is True
            assert status == 200

            db.session.refresh(user)
            assert user.subscription_active is True
            assert user.subscription_plan == "dawnotemu_monthly"
            assert user.subscription_will_renew is True
            assert user.subscription_expires_at is not None
            assert user.subscription_source == "app_store"

    def test_initial_purchase_grants_credits(self, app):
        with app.app_context():
            user = _create_user()
            user.revenuecat_app_user_id = "rc_credits"
            db.session.commit()

            balance_before = user.credits_balance

            payload = _webhook_payload("INITIAL_PURCHASE", "rc_credits")
            SubscriptionController.handle_revenuecat_webhook(payload)

            db.session.refresh(user)
            assert user.credits_balance > balance_before

    def test_renewal_extends_subscription(self, app):
        with app.app_context():
            user = _create_user()
            user.revenuecat_app_user_id = "rc_renew"
            user.subscription_active = True
            user.subscription_expires_at = datetime.utcnow() + timedelta(days=5)
            db.session.commit()

            new_expiry_ms = int((datetime.utcnow() + timedelta(days=35)).timestamp() * 1000)
            payload = _webhook_payload("RENEWAL", "rc_renew", expiration_at_ms=new_expiry_ms)
            ok, data, status = SubscriptionController.handle_revenuecat_webhook(payload)
            assert ok is True

            db.session.refresh(user)
            assert user.subscription_active is True
            assert user.subscription_will_renew is True
            # New expiry should be ~35 days out
            assert user.subscription_expires_at > datetime.utcnow() + timedelta(days=30)

    def test_cancellation_clears_will_renew(self, app):
        with app.app_context():
            user = _create_user()
            user.revenuecat_app_user_id = "rc_cancel"
            user.subscription_active = True
            user.subscription_will_renew = True
            user.subscription_expires_at = datetime.utcnow() + timedelta(days=20)
            db.session.commit()

            payload = _webhook_payload("CANCELLATION", "rc_cancel")
            ok, data, status = SubscriptionController.handle_revenuecat_webhook(payload)
            assert ok is True

            db.session.refresh(user)
            assert user.subscription_will_renew is False
            # Subscription stays active until expiry
            assert user.subscription_active is True

    def test_uncancellation_restores_will_renew(self, app):
        with app.app_context():
            user = _create_user()
            user.revenuecat_app_user_id = "rc_uncancel"
            user.subscription_active = True
            user.subscription_will_renew = False
            user.subscription_expires_at = datetime.utcnow() + timedelta(days=20)
            db.session.commit()

            payload = _webhook_payload("UNCANCELLATION", "rc_uncancel")
            ok, data, status = SubscriptionController.handle_revenuecat_webhook(payload)
            assert ok is True

            db.session.refresh(user)
            assert user.subscription_will_renew is True

    def test_expiration_deactivates_subscription(self, app):
        with app.app_context():
            user = _create_user()
            user.revenuecat_app_user_id = "rc_expire"
            user.subscription_active = True
            user.subscription_will_renew = False
            user.subscription_expires_at = datetime.utcnow() - timedelta(hours=1)
            db.session.commit()

            payload = _webhook_payload("EXPIRATION", "rc_expire")
            ok, data, status = SubscriptionController.handle_revenuecat_webhook(payload)
            assert ok is True

            db.session.refresh(user)
            assert user.subscription_active is False
            assert user.subscription_will_renew is False

    def test_billing_issue_sets_timestamp(self, app):
        with app.app_context():
            user = _create_user()
            user.revenuecat_app_user_id = "rc_billing"
            user.subscription_active = True
            user.subscription_expires_at = datetime.utcnow() + timedelta(days=20)
            db.session.commit()

            payload = _webhook_payload("BILLING_ISSUE", "rc_billing")
            ok, data, status = SubscriptionController.handle_revenuecat_webhook(payload)
            assert ok is True

            db.session.refresh(user)
            assert user.billing_issue_at is not None

    def test_product_change_updates_plan(self, app):
        with app.app_context():
            user = _create_user()
            user.revenuecat_app_user_id = "rc_change"
            user.subscription_active = True
            user.subscription_plan = "dawnotemu_monthly"
            user.subscription_expires_at = datetime.utcnow() + timedelta(days=20)
            db.session.commit()

            payload = _webhook_payload(
                "PRODUCT_CHANGE", "rc_change",
                new_product_id="dawnotemu_annual",
            )
            ok, data, status = SubscriptionController.handle_revenuecat_webhook(payload)
            assert ok is True

            db.session.refresh(user)
            assert user.subscription_plan == "dawnotemu_annual"

    def test_idempotent_duplicate_event(self, app):
        with app.app_context():
            user = _create_user()
            user.revenuecat_app_user_id = "rc_dedup"
            db.session.commit()

            payload = _webhook_payload("INITIAL_PURCHASE", "rc_dedup", event_id="dup_123")

            ok1, data1, status1 = SubscriptionController.handle_revenuecat_webhook(payload)
            assert ok1 is True
            assert status1 == 200

            ok2, data2, status2 = SubscriptionController.handle_revenuecat_webhook(payload)
            assert ok2 is True
            assert data2["status"] == "already_processed"

    def test_webhook_event_recorded(self, app):
        with app.app_context():
            user = _create_user()
            user.revenuecat_app_user_id = "rc_recorded"
            db.session.commit()

            evt_id = "evt_recorded_1"
            payload = _webhook_payload("INITIAL_PURCHASE", "rc_recorded", event_id=evt_id)
            SubscriptionController.handle_revenuecat_webhook(payload)

            stored = WebhookEvent.query.filter_by(event_id=evt_id).first()
            assert stored is not None
            assert stored.event_type == "INITIAL_PURCHASE"

    def test_unhandled_event_type_recorded_returns_200(self, app):
        with app.app_context():
            user = _create_user()
            user.revenuecat_app_user_id = "rc_unknown"
            db.session.commit()

            evt_id = "evt_unknown_type"
            payload = _webhook_payload("SUBSCRIBER_ALIAS", "rc_unknown", event_id=evt_id)
            ok, data, status = SubscriptionController.handle_revenuecat_webhook(payload)
            assert ok is True
            assert status == 200
            assert data["status"] == "ignored"

            stored = WebhookEvent.query.filter_by(event_id=evt_id).first()
            assert stored is not None


# ---------------------------------------------------------------------------
# 5. Webhook HTTP endpoint — auth and payload validation
# ---------------------------------------------------------------------------

class TestWebhookHTTPEndpoint:

    def test_missing_auth_returns_401(self, client):
        resp = client.post(
            "/api/webhooks/revenuecat",
            data=json.dumps({"event": {"type": "TEST", "id": "t1"}}),
            content_type="application/json",
        )
        assert resp.status_code == 401

    def test_wrong_secret_returns_401(self, client):
        resp = client.post(
            "/api/webhooks/revenuecat",
            headers={"Authorization": "Bearer wrong-secret"},
            data=json.dumps({"event": {"type": "TEST", "id": "t2"}}),
            content_type="application/json",
        )
        assert resp.status_code == 401

    def test_valid_auth_with_test_event(self, client):
        resp = client.post(
            "/api/webhooks/revenuecat",
            headers={"Authorization": "Bearer test-webhook-secret"},
            data=json.dumps({"event": {"type": "TEST", "id": "t3"}}),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_valid_auth_bearer_prefix(self, client):
        resp = client.post(
            "/api/webhooks/revenuecat",
            headers={"Authorization": "test-webhook-secret"},
            data=json.dumps({"event": {"type": "TEST", "id": "t4"}}),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_malformed_json_returns_400(self, client):
        resp = client.post(
            "/api/webhooks/revenuecat",
            headers={"Authorization": "Bearer test-webhook-secret"},
            data="not json",
            content_type="application/json",
        )
        # Either 400 (malformed JSON) or 400 (invalid payload)
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 6. Subscription status HTTP endpoint
# ---------------------------------------------------------------------------

class TestSubscriptionStatusHTTPEndpoint:

    def test_returns_status_for_authenticated_user(self, app, client):
        with app.app_context():
            user = _create_user()
            headers = _auth_header(app, user)

        resp = client.get("/api/user/subscription-status", headers=headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert "trial" in body
        assert "subscription" in body
        assert "can_generate" in body

    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/api/user/subscription-status")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# 7. Link RevenueCat HTTP endpoint
# ---------------------------------------------------------------------------

class TestLinkRevenueCatHTTPEndpoint:

    def test_link_via_http(self, app, client):
        with app.app_context():
            user = _create_user()
            headers = _auth_header(app, user)

        resp = client.post(
            "/api/user/link-revenuecat",
            headers=headers,
            data=json.dumps({"revenuecat_app_user_id": "rc_http_test"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["revenuecat_app_user_id"] == "rc_http_test"

    def test_link_missing_body_returns_400(self, app, client):
        with app.app_context():
            user = _create_user()
            headers = _auth_header(app, user)

        resp = client.post("/api/user/link-revenuecat", headers=headers)
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 8. Addon grant — controller level
# ---------------------------------------------------------------------------

class TestAddonGrantController:

    def test_unknown_product_rejected(self, app):
        with app.app_context():
            user = _create_user()
            user.subscription_active = True
            user.subscription_expires_at = datetime.utcnow() + timedelta(days=30)
            db.session.commit()

            ok, data, status = AddonController.grant_addon(user, "receipt_1", "unknown_product", "ios")
            assert ok is False
            assert status == 400

    def test_invalid_platform_rejected(self, app):
        with app.app_context():
            user = _create_user()
            user.subscription_active = True
            user.subscription_expires_at = datetime.utcnow() + timedelta(days=30)
            db.session.commit()

            ok, data, status = AddonController.grant_addon(user, "receipt_1", "credits_10", "windows")
            assert ok is False
            assert status == 400

    def test_no_subscription_rejected(self, app):
        with app.app_context():
            user = _create_user()
            user.trial_expires_at = datetime.utcnow() - timedelta(days=1)
            db.session.commit()

            ok, data, status = AddonController.grant_addon(user, "receipt_1", "credits_10", "ios")
            assert ok is False
            assert status == 403

    def test_grant_success_in_dev_mode(self, app):
        """In dev/test mode, receipt validation is skipped when REVENUECAT_API_KEY is set
        but FLASK_ENV=testing. We patch the validator to return True."""
        import os
        with app.app_context():
            user = _create_user()
            user.subscription_active = True
            user.subscription_expires_at = datetime.utcnow() + timedelta(days=30)
            user.revenuecat_app_user_id = "rc_addon"
            db.session.commit()

            balance_before = user.credits_balance

            from unittest.mock import patch
            with patch(
                "controllers.addon_controller._validate_receipt_with_revenuecat",
                return_value=True,
            ):
                ok, data, status = AddonController.grant_addon(
                    user, "receipt_addon_1", "credits_10", "ios",
                )

            assert ok is True
            assert status == 200
            assert data["credits_granted"] == 10

            db.session.refresh(user)
            assert user.credits_balance == balance_before + 10

    def test_duplicate_receipt_idempotent(self, app):
        """Same receipt token returns idempotent success for same user."""
        from unittest.mock import patch
        with app.app_context():
            user = _create_user()
            user.subscription_active = True
            user.subscription_expires_at = datetime.utcnow() + timedelta(days=30)
            user.revenuecat_app_user_id = "rc_dup_addon"
            db.session.commit()

            with patch(
                "controllers.addon_controller._validate_receipt_with_revenuecat",
                return_value=True,
            ):
                ok1, data1, s1 = AddonController.grant_addon(user, "dup_receipt", "credits_10", "ios")
                assert ok1 is True

                ok2, data2, s2 = AddonController.grant_addon(user, "dup_receipt", "credits_10", "ios")
                assert ok2 is True
                assert s2 == 200

    def test_duplicate_receipt_different_user_rejected(self, app):
        from unittest.mock import patch
        with app.app_context():
            user1 = _create_user("u1@test.com")
            user1.subscription_active = True
            user1.subscription_expires_at = datetime.utcnow() + timedelta(days=30)
            user1.revenuecat_app_user_id = "rc_u1"

            user2 = _create_user("u2@test.com")
            user2.subscription_active = True
            user2.subscription_expires_at = datetime.utcnow() + timedelta(days=30)
            user2.revenuecat_app_user_id = "rc_u2"
            db.session.commit()

            with patch(
                "controllers.addon_controller._validate_receipt_with_revenuecat",
                return_value=True,
            ):
                AddonController.grant_addon(user1, "shared_receipt", "credits_10", "ios")
                ok, data, status = AddonController.grant_addon(user2, "shared_receipt", "credits_10", "ios")

            assert ok is False
            assert status == 409


# ---------------------------------------------------------------------------
# 9. Full lifecycle: trial -> subscribe -> use -> cancel -> expire
# ---------------------------------------------------------------------------

class TestFullLifecycle:

    def test_complete_user_journey(self, app):
        with app.app_context():
            # Step 1: New user with trial
            user = _create_user("journey@test.com")
            assert user.trial_is_active is True
            assert user.can_generate is True

            # Step 2: Link RevenueCat
            ok, _, _ = SubscriptionController.link_revenuecat(user, "rc_journey")
            assert ok is True

            # Step 3: Trial expires
            user.trial_expires_at = datetime.utcnow() - timedelta(days=1)
            db.session.commit()
            db.session.refresh(user)
            assert user.can_generate is False

            # Step 4: Initial purchase via webhook
            payload = _webhook_payload("INITIAL_PURCHASE", "rc_journey")
            ok, _, status = SubscriptionController.handle_revenuecat_webhook(payload)
            assert ok is True
            db.session.refresh(user)
            assert user.subscription_is_active is True
            assert user.can_generate is True

            # Step 5: Cancellation (still active until period ends)
            payload = _webhook_payload("CANCELLATION", "rc_journey")
            ok, _, _ = SubscriptionController.handle_revenuecat_webhook(payload)
            db.session.refresh(user)
            assert user.subscription_will_renew is False
            assert user.subscription_is_active is True  # Still active

            # Step 6: Expiration
            payload = _webhook_payload("EXPIRATION", "rc_journey")
            ok, _, _ = SubscriptionController.handle_revenuecat_webhook(payload)
            db.session.refresh(user)
            assert user.subscription_active is False
            assert user.can_generate is False
