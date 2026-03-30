import os
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

from database import db
from models.user_model import User
from models.credit_model import grant as credit_grant
from controllers.auth_controller import AuthController


WEBHOOK_SECRET = os.environ.get("REVENUECAT_WEBHOOK_SECRET", "test-webhook-secret")


def _create_user(app, email, trial_days=14, subscription_active=False,
                 subscription_plan=None, subscription_will_renew=False,
                 revenuecat_id=None, credits=0):
    with app.app_context():
        trial_at = (
            datetime.utcnow() + timedelta(days=trial_days)
            if trial_days is not None
            else None
        )
        user = User(
            email=email,
            is_active=True,
            email_confirmed=True,
            credits_balance=0,
            trial_expires_at=trial_at,
            subscription_active=subscription_active,
            subscription_plan=subscription_plan,
            subscription_will_renew=subscription_will_renew,
            revenuecat_app_user_id=revenuecat_id,
        )
        user.set_password("TestPass123!")
        db.session.add(user)
        db.session.commit()

        if credits > 0:
            credit_grant(user.id, credits, reason="test_seed", source="free")
            db.session.refresh(user)

        token = AuthController.generate_access_token(user, expires_delta=timedelta(minutes=30))
        return user.id, token


def _auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def _webhook_header():
    return {"Authorization": WEBHOOK_SECRET, "Content-Type": "application/json"}


def _make_payload(event_type, app_user_id, event_id=None, product_id="dawnotemu_monthly",
                  store="APP_STORE", expiration_days=30):
    return {
        "api_version": "1.0",
        "event": {
            "type": event_type,
            "id": event_id or str(uuid.uuid4()),
            "app_user_id": str(app_user_id),
            "product_id": product_id,
            "store": store,
            "expiration_at_ms": int(
                (datetime.utcnow() + timedelta(days=expiration_days)).timestamp() * 1000
            ),
        },
    }


# ─── GET /api/user/subscription-status ───────────────────────────────────


class TestSubscriptionStatusRoute:

    def test_authenticated_returns_correct_shape(self, client, app):
        _, token = _create_user(app, "status-shape@example.com")
        resp = client.get("/api/user/subscription-status", headers=_auth_header(token))

        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data["trial"], dict)
        assert isinstance(data["can_generate"], bool)
        assert "initial_credits" in data

    def test_unauthenticated_returns_401(self, client, app):
        resp = client.get("/api/user/subscription-status")
        assert resp.status_code == 401

    def test_trial_active(self, client, app):
        _, token = _create_user(app, "trial-route@example.com", trial_days=7)
        resp = client.get("/api/user/subscription-status", headers=_auth_header(token))

        data = resp.get_json()
        assert data["trial"]["active"] is True
        assert data["can_generate"] is True

    def test_subscription_active(self, client, app):
        user_id, token = _create_user(
            app, "sub-route@example.com",
            trial_days=-1,
            subscription_active=True,
            subscription_plan="monthly",
        )
        with app.app_context():
            user = db.session.get(User, user_id)
            user.subscription_expires_at = datetime.utcnow() + timedelta(days=30)
            db.session.commit()
        resp = client.get("/api/user/subscription-status", headers=_auth_header(token))

        data = resp.get_json()
        assert data["subscription"]["active"] is True
        assert data["can_generate"] is True


# ─── POST /api/webhooks/revenuecat ───────────────────────────────────────


class TestWebhookRoute:

    def test_initial_purchase(self, client, app):
        user_id, _ = _create_user(
            app, "webhook-init@example.com", trial_days=-1,
        )
        with app.app_context():
            user = db.session.get(User, user_id)
            user.revenuecat_app_user_id = str(user_id)
            db.session.commit()

        payload = _make_payload("INITIAL_PURCHASE", user_id)
        resp = client.post("/api/webhooks/revenuecat", json=payload, headers=_webhook_header())

        assert resp.status_code == 200
        with app.app_context():
            user = db.session.get(User, user_id)
            assert user.subscription_active is True
            assert user.subscription_will_renew is True
            assert user.credits_balance == 26

    def test_renewal_grants_credits(self, client, app):
        user_id, _ = _create_user(
            app, "webhook-renew@example.com",
            trial_days=-1,
            subscription_active=True,
        )
        with app.app_context():
            user = db.session.get(User, user_id)
            user.revenuecat_app_user_id = str(user_id)
            db.session.commit()

        payload = _make_payload("RENEWAL", user_id)
        resp = client.post("/api/webhooks/revenuecat", json=payload, headers=_webhook_header())

        assert resp.status_code == 200
        with app.app_context():
            user = db.session.get(User, user_id)
            assert user.credits_balance == 26

    def test_initial_purchase_yearly_grants_30_credits(self, client, app):
        user_id, _ = _create_user(
            app, "webhook-yearly@example.com", trial_days=-1,
        )
        with app.app_context():
            user = db.session.get(User, user_id)
            user.revenuecat_app_user_id = str(user_id)
            db.session.commit()

        payload = _make_payload("INITIAL_PURCHASE", user_id, product_id="dawnotemu_annual")
        resp = client.post("/api/webhooks/revenuecat", json=payload, headers=_webhook_header())

        assert resp.status_code == 200
        with app.app_context():
            user = db.session.get(User, user_id)
            assert user.subscription_active is True
            assert user.subscription_plan == "dawnotemu_annual"
            assert user.credits_balance == 30  # yearly gets 30, not 26

    def test_renewal_yearly_grants_30_credits(self, client, app):
        user_id, _ = _create_user(
            app, "webhook-yearly-renew@example.com",
            trial_days=-1,
            subscription_active=True,
            subscription_plan="dawnotemu_annual",
        )
        with app.app_context():
            user = db.session.get(User, user_id)
            user.revenuecat_app_user_id = str(user_id)
            db.session.commit()

        payload = _make_payload("RENEWAL", user_id, product_id="dawnotemu_annual")
        resp = client.post("/api/webhooks/revenuecat", json=payload, headers=_webhook_header())

        assert resp.status_code == 200
        with app.app_context():
            user = db.session.get(User, user_id)
            assert user.credits_balance == 30

    def test_cancellation_sets_will_renew_false(self, client, app):
        user_id, _ = _create_user(
            app, "webhook-cancel@example.com",
            subscription_active=True,
            subscription_will_renew=True,
        )
        with app.app_context():
            user = db.session.get(User, user_id)
            user.revenuecat_app_user_id = str(user_id)
            db.session.commit()

        payload = _make_payload("CANCELLATION", user_id)
        resp = client.post("/api/webhooks/revenuecat", json=payload, headers=_webhook_header())

        assert resp.status_code == 200
        with app.app_context():
            user = db.session.get(User, user_id)
            assert user.subscription_will_renew is False
            assert user.subscription_active is True  # still active until period end

    def test_expiration_deactivates(self, client, app):
        user_id, _ = _create_user(
            app, "webhook-expire@example.com",
            subscription_active=True,
        )
        with app.app_context():
            user = db.session.get(User, user_id)
            user.revenuecat_app_user_id = str(user_id)
            db.session.commit()

        payload = _make_payload("EXPIRATION", user_id)
        resp = client.post("/api/webhooks/revenuecat", json=payload, headers=_webhook_header())

        assert resp.status_code == 200
        with app.app_context():
            user = db.session.get(User, user_id)
            assert user.subscription_active is False

    def test_invalid_auth_returns_401(self, client, app):
        payload = _make_payload("TEST", "999")
        resp = client.post(
            "/api/webhooks/revenuecat",
            json=payload,
            headers={"Authorization": "wrong-secret", "Content-Type": "application/json"},
        )
        assert resp.status_code == 401

    def test_duplicate_event_is_idempotent(self, client, app):
        user_id, _ = _create_user(app, "webhook-dup@example.com", trial_days=-1)
        with app.app_context():
            user = db.session.get(User, user_id)
            user.revenuecat_app_user_id = str(user_id)
            db.session.commit()

        event_id = str(uuid.uuid4())
        payload = _make_payload("INITIAL_PURCHASE", user_id, event_id=event_id)

        resp1 = client.post("/api/webhooks/revenuecat", json=payload, headers=_webhook_header())
        resp2 = client.post("/api/webhooks/revenuecat", json=payload, headers=_webhook_header())

        assert resp1.status_code == 200
        assert resp2.status_code == 200

        with app.app_context():
            user = db.session.get(User, user_id)
            # Credits should be granted only once (26, not 52)
            assert user.credits_balance == 26

    def test_test_event_returns_200(self, client, app):
        payload = _make_payload("TEST", "999")
        resp = client.post("/api/webhooks/revenuecat", json=payload, headers=_webhook_header())

        assert resp.status_code == 200

    def test_missing_auth_header_returns_401(self, client, app):
        payload = _make_payload("TEST", "999")
        resp = client.post(
            "/api/webhooks/revenuecat",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 401

    def test_empty_auth_header_returns_401(self, client, app):
        payload = _make_payload("TEST", "999")
        resp = client.post(
            "/api/webhooks/revenuecat",
            json=payload,
            headers={"Authorization": "", "Content-Type": "application/json"},
        )
        assert resp.status_code == 401

    def test_empty_body_returns_400(self, client, app):
        resp = client.post(
            "/api/webhooks/revenuecat",
            data=b"",
            headers={"Authorization": WEBHOOK_SECRET, "Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    def test_malformed_json_returns_400(self, client, app):
        resp = client.post(
            "/api/webhooks/revenuecat",
            data=b"{invalid json",
            headers={"Authorization": WEBHOOK_SECRET, "Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    def test_unknown_user_returns_404(self, client, app):
        payload = _make_payload("INITIAL_PURCHASE", "nonexistent-user-id")
        resp = client.post("/api/webhooks/revenuecat", json=payload, headers=_webhook_header())

        assert resp.status_code == 404

    def test_product_change_updates_plan(self, client, app):
        user_id, _ = _create_user(
            app, "webhook-planchange@example.com",
            subscription_active=True,
            subscription_plan="dawnotemu_monthly",
        )
        with app.app_context():
            user = db.session.get(User, user_id)
            user.revenuecat_app_user_id = str(user_id)
            db.session.commit()

        payload = {
            "api_version": "1.0",
            "event": {
                "type": "PRODUCT_CHANGE",
                "id": str(uuid.uuid4()),
                "app_user_id": str(user_id),
                "new_product_id": "dawnotemu_annual",
                "product_id": "dawnotemu_monthly",
                "store": "APP_STORE",
            },
        }
        resp = client.post("/api/webhooks/revenuecat", json=payload, headers=_webhook_header())

        assert resp.status_code == 200
        with app.app_context():
            user = db.session.get(User, user_id)
            assert user.subscription_plan == "dawnotemu_annual"

    def test_billing_issue_sets_flag(self, client, app):
        user_id, _ = _create_user(
            app, "webhook-billing@example.com",
            subscription_active=True,
        )
        with app.app_context():
            user = db.session.get(User, user_id)
            user.revenuecat_app_user_id = str(user_id)
            db.session.commit()

        payload = _make_payload("BILLING_ISSUE", user_id)
        resp = client.post("/api/webhooks/revenuecat", json=payload, headers=_webhook_header())

        assert resp.status_code == 200
        with app.app_context():
            user = db.session.get(User, user_id)
            assert user.billing_issue_at is not None
            assert user.subscription_active is True  # still active

    def test_uncancellation_sets_will_renew_true(self, client, app):
        user_id, _ = _create_user(
            app, "webhook-uncancel@example.com",
            subscription_active=True,
            subscription_will_renew=False,
        )
        with app.app_context():
            user = db.session.get(User, user_id)
            user.revenuecat_app_user_id = str(user_id)
            db.session.commit()

        payload = _make_payload("UNCANCELLATION", user_id)
        resp = client.post("/api/webhooks/revenuecat", json=payload, headers=_webhook_header())

        assert resp.status_code == 200
        with app.app_context():
            user = db.session.get(User, user_id)
            assert user.subscription_will_renew is True

    def test_unhandled_event_type_returns_200(self, client, app):
        user_id, _ = _create_user(app, "webhook-alias@example.com")
        with app.app_context():
            user = db.session.get(User, user_id)
            user.revenuecat_app_user_id = str(user_id)
            db.session.commit()

        payload = _make_payload("SUBSCRIBER_ALIAS", user_id)
        resp = client.post("/api/webhooks/revenuecat", json=payload, headers=_webhook_header())

        assert resp.status_code == 200

    def test_renewal_clears_billing_issue(self, client, app):
        user_id, _ = _create_user(
            app, "webhook-billing-clear@example.com",
            trial_days=-1,
            subscription_active=True,
        )
        with app.app_context():
            user = db.session.get(User, user_id)
            user.revenuecat_app_user_id = str(user_id)
            user.billing_issue_at = datetime.utcnow()
            db.session.commit()

        payload = _make_payload("RENEWAL", user_id)
        resp = client.post("/api/webhooks/revenuecat", json=payload, headers=_webhook_header())

        assert resp.status_code == 200
        with app.app_context():
            user = db.session.get(User, user_id)
            assert user.billing_issue_at is None

    def test_bearer_prefix_auth_accepted(self, client, app):
        """Webhook should accept Authorization header with Bearer prefix."""
        payload = _make_payload("TEST", "999")
        resp = client.post(
            "/api/webhooks/revenuecat",
            json=payload,
            headers={"Authorization": f"Bearer {WEBHOOK_SECRET}", "Content-Type": "application/json"},
        )
        assert resp.status_code == 200


# ─── POST /api/user/link-revenuecat ──────────────────────────────────────


class TestLinkRevenueCatRoute:

    def test_link_success(self, client, app):
        _, token = _create_user(app, "link-ok@example.com")
        resp = client.post(
            "/api/user/link-revenuecat",
            json={"revenuecat_app_user_id": "rc_user_123"},
            headers=_auth_header(token),
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "linked"
        assert data["revenuecat_app_user_id"] == "rc_user_123"

    def test_link_missing_id_returns_400(self, client, app):
        _, token = _create_user(app, "link-missing@example.com")
        resp = client.post(
            "/api/user/link-revenuecat",
            json={"revenuecat_app_user_id": ""},
            headers=_auth_header(token),
        )
        assert resp.status_code == 400

    def test_link_conflict_returns_409(self, client, app):
        user1_id, _ = _create_user(app, "link-conflict1@example.com")
        _, token2 = _create_user(app, "link-conflict2@example.com")

        with app.app_context():
            user1 = db.session.get(User, user1_id)
            user1.revenuecat_app_user_id = "rc_taken"
            db.session.commit()

        resp = client.post(
            "/api/user/link-revenuecat",
            json={"revenuecat_app_user_id": "rc_taken"},
            headers=_auth_header(token2),
        )
        assert resp.status_code == 409

    def test_link_too_long_id_returns_400(self, client, app):
        _, token = _create_user(app, "link-long@example.com")
        long_id = "x" * 101
        resp = client.post(
            "/api/user/link-revenuecat",
            json={"revenuecat_app_user_id": long_id},
            headers=_auth_header(token),
        )
        assert resp.status_code == 400

    def test_link_unauthenticated_returns_401(self, client, app):
        resp = client.post(
            "/api/user/link-revenuecat",
            json={"revenuecat_app_user_id": "rc_user_456"},
        )
        assert resp.status_code == 401


# ─── POST /api/credits/grant-addon ───────────────────────────────────────


class TestGrantAddonRoute:

    def _create_subscribed_user(self, app, email, credits=0):
        user_id, token = _create_user(
            app, email,
            trial_days=-1,
            subscription_active=True,
            subscription_plan="monthly",
            credits=credits,
        )
        with app.app_context():
            user = db.session.get(User, user_id)
            user.subscription_expires_at = datetime.utcnow() + timedelta(days=30)
            db.session.commit()
        return user_id, token

    @patch("controllers.addon_controller._validate_receipt_with_revenuecat", return_value=True)
    def test_grant_addon_success(self, mock_validate, client, app):
        _, token = self._create_subscribed_user(app, "addon-ok@example.com", credits=10)
        resp = client.post(
            "/api/credits/grant-addon",
            json={"receipt_token": "rc_route_ok", "product_id": "credits_10", "platform": "ios"},
            headers=_auth_header(token),
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["credits_granted"] == 10
        assert data["new_balance"] == 20

    @patch("controllers.addon_controller._validate_receipt_with_revenuecat", return_value=True)
    def test_grant_addon_idempotent(self, mock_validate, client, app):
        _, token = self._create_subscribed_user(app, "addon-idem@example.com", credits=10)
        body = {"receipt_token": "rc_route_idem", "product_id": "credits_10", "platform": "ios"}

        client.post("/api/credits/grant-addon", json=body, headers=_auth_header(token))
        resp = client.post("/api/credits/grant-addon", json=body, headers=_auth_header(token))

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["credits_granted"] == 10
        assert data["new_balance"] == 20  # not 30

    def test_grant_addon_non_subscriber_403(self, client, app):
        _, token = _create_user(app, "addon-nosub@example.com", trial_days=-1)
        resp = client.post(
            "/api/credits/grant-addon",
            json={"receipt_token": "rc_nosub", "product_id": "credits_10", "platform": "ios"},
            headers=_auth_header(token),
        )
        assert resp.status_code == 403

    def test_grant_addon_invalid_product_400(self, client, app):
        _, token = self._create_subscribed_user(app, "addon-badprod@example.com")
        resp = client.post(
            "/api/credits/grant-addon",
            json={"receipt_token": "rc_badprod", "product_id": "credits_999", "platform": "ios"},
            headers=_auth_header(token),
        )
        assert resp.status_code == 400

    def test_grant_addon_missing_fields_400(self, client, app):
        _, token = self._create_subscribed_user(app, "addon-missing@example.com")
        resp = client.post(
            "/api/credits/grant-addon",
            json={"receipt_token": "rc_miss"},
            headers=_auth_header(token),
        )
        assert resp.status_code == 400
