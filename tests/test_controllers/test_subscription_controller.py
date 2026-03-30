from datetime import datetime, timedelta
from unittest.mock import patch

from database import db
from models.user_model import User
from controllers.subscription_controller import SubscriptionController


def _create_user(email="sub-ctrl@example.com", trial_days=14,
                 subscription_active=False, subscription_plan=None,
                 subscription_will_renew=False, revenuecat_id=None):
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
    return user


class TestGetSubscriptionStatus:

    def test_response_shape(self, app):
        with app.app_context():
            user = _create_user("shape@example.com")
            success, data, status = SubscriptionController.get_subscription_status(user)

            assert success is True
            assert status == 200
            assert "trial" in data
            assert "subscription" in data
            assert "can_generate" in data
            assert "initial_credits" in data
            assert "active" in data["trial"]
            assert "expires_at" in data["trial"]
            assert "days_remaining" in data["trial"]
            assert "active" in data["subscription"]
            assert "plan" in data["subscription"]
            assert "expires_at" in data["subscription"]
            assert "will_renew" in data["subscription"]

    def test_trial_active(self, app):
        with app.app_context():
            user = _create_user("trial-active@example.com", trial_days=5)
            _, data, _ = SubscriptionController.get_subscription_status(user)

            assert data["trial"]["active"] is True
            assert data["trial"]["days_remaining"] in (4, 5)
            assert data["can_generate"] is True

    def test_trial_expired(self, app):
        with app.app_context():
            user = _create_user("trial-expired@example.com", trial_days=-1)
            _, data, _ = SubscriptionController.get_subscription_status(user)

            assert data["trial"]["active"] is False
            assert data["trial"]["days_remaining"] == 0
            assert data["can_generate"] is False

    def test_trial_null(self, app):
        with app.app_context():
            user = _create_user("trial-null@example.com", trial_days=None)
            _, data, _ = SubscriptionController.get_subscription_status(user)

            assert data["trial"]["active"] is False
            assert data["trial"]["expires_at"] is None
            assert data["can_generate"] is False

    def test_subscription_active(self, app):
        with app.app_context():
            user = _create_user(
                "sub-active@example.com",
                trial_days=-1,
                subscription_active=True,
                subscription_plan="monthly",
                subscription_will_renew=True,
            )
            user.subscription_expires_at = datetime.utcnow() + timedelta(days=30)
            db.session.commit()
            _, data, _ = SubscriptionController.get_subscription_status(user)

            assert data["subscription"]["active"] is True
            assert data["subscription"]["plan"] == "monthly"
            assert data["subscription"]["will_renew"] is True
            assert data["can_generate"] is True

    def test_can_generate_requires_trial_or_subscription(self, app):
        with app.app_context():
            user = _create_user("no-access@example.com", trial_days=-1)
            _, data, _ = SubscriptionController.get_subscription_status(user)

            assert data["can_generate"] is False

    def test_days_remaining_calculation(self, app):
        with app.app_context():
            user = _create_user("days-calc@example.com", trial_days=12)
            _, data, _ = SubscriptionController.get_subscription_status(user)

            assert data["trial"]["days_remaining"] in (11, 12)


class TestHandleWebhook:

    def _make_payload(self, event_type, app_user_id, event_id="evt-1",
                      product_id="dawnotemu_monthly", store="APP_STORE",
                      expiration_days=30, extra_event_fields=None):
        event = {
            "type": event_type,
            "id": event_id,
            "app_user_id": str(app_user_id),
            "product_id": product_id,
            "store": store,
            "expiration_at_ms": int(
                (datetime.utcnow() + timedelta(days=expiration_days)).timestamp() * 1000
            ),
        }
        if extra_event_fields:
            event.update(extra_event_fields)
        return {"api_version": "1.0", "event": event}

    def test_handler_exception_rolls_back(self, app):
        """If handler raises, user state must not be mutated."""
        with app.app_context():
            user = _create_user(
                "handler-exc@example.com",
                trial_days=-1,
                revenuecat_id="rc_handler_exc",
            )
            assert user.subscription_active is False

            with patch(
                "controllers.subscription_controller.credit_grant",
                side_effect=RuntimeError("boom"),
            ):
                payload = self._make_payload("INITIAL_PURCHASE", "rc_handler_exc")
                success, data, status = SubscriptionController.handle_revenuecat_webhook(payload)

            assert success is False
            assert status == 500

            db.session.refresh(user)
            # Rollback should have undone subscription_active = True
            assert user.subscription_active is False
            assert user.credits_balance == 0

    def test_initial_purchase_clears_billing_issue(self, app):
        with app.app_context():
            user = _create_user(
                "billing-clear-init@example.com",
                trial_days=-1,
                revenuecat_id="rc_billing_clear_init",
            )
            user.billing_issue_at = datetime.utcnow()
            db.session.commit()

            payload = self._make_payload("INITIAL_PURCHASE", "rc_billing_clear_init")
            success, _, status = SubscriptionController.handle_revenuecat_webhook(payload)

            assert status == 200
            db.session.refresh(user)
            assert user.billing_issue_at is None

    def test_renewal_clears_billing_issue(self, app):
        with app.app_context():
            user = _create_user(
                "billing-clear-renew@example.com",
                trial_days=-1,
                subscription_active=True,
                revenuecat_id="rc_billing_clear_renew",
            )
            user.billing_issue_at = datetime.utcnow()
            db.session.commit()

            payload = self._make_payload("RENEWAL", "rc_billing_clear_renew")
            success, _, status = SubscriptionController.handle_revenuecat_webhook(payload)

            assert status == 200
            db.session.refresh(user)
            assert user.billing_issue_at is None

    def test_uncancellation_sets_will_renew_true(self, app):
        with app.app_context():
            user = _create_user(
                "uncancellation@example.com",
                subscription_active=True,
                subscription_will_renew=False,
                revenuecat_id="rc_uncancel",
            )

            payload = self._make_payload("UNCANCELLATION", "rc_uncancel")
            success, _, status = SubscriptionController.handle_revenuecat_webhook(payload)

            assert status == 200
            db.session.refresh(user)
            assert user.subscription_will_renew is True

    def test_product_change_updates_expiration(self, app):
        with app.app_context():
            user = _create_user(
                "product-change-exp@example.com",
                subscription_active=True,
                subscription_plan="dawnotemu_monthly",
                revenuecat_id="rc_prod_change_exp",
            )
            old_expiry = datetime.utcnow() + timedelta(days=5)
            user.subscription_expires_at = old_expiry
            db.session.commit()

            payload = self._make_payload(
                "PRODUCT_CHANGE", "rc_prod_change_exp",
                event_id="evt-prodchange",
                extra_event_fields={"new_product_id": "dawnotemu_annual"},
                expiration_days=365,
            )
            success, _, status = SubscriptionController.handle_revenuecat_webhook(payload)

            assert status == 200
            db.session.refresh(user)
            assert user.subscription_plan == "dawnotemu_annual"
            assert user.subscription_expires_at > old_expiry

    def test_unhandled_event_type_returns_200(self, app):
        with app.app_context():
            user = _create_user(
                "unhandled@example.com",
                revenuecat_id="rc_unhandled",
            )
            payload = self._make_payload("SUBSCRIBER_ALIAS", "rc_unhandled", event_id="evt-alias")
            success, data, status = SubscriptionController.handle_revenuecat_webhook(payload)

            assert success is True
            assert status == 200
            assert data["status"] == "ignored"

    def test_initial_purchase_sets_plan_to_none_when_missing(self, app):
        """product_id fallback should be None, not 'monthly'."""
        with app.app_context():
            user = _create_user(
                "no-product@example.com",
                trial_days=-1,
                revenuecat_id="rc_no_product",
            )
            payload = self._make_payload(
                "INITIAL_PURCHASE", "rc_no_product",
                event_id="evt-noprod",
                product_id="",
            )
            success, _, status = SubscriptionController.handle_revenuecat_webhook(payload)

            assert status == 200
            db.session.refresh(user)
            assert user.subscription_plan is None

    def test_initial_purchase_activates_subscription(self, app):
        """INITIAL_PURCHASE must set all core subscription fields."""
        with app.app_context():
            user = _create_user(
                "init-purchase@example.com",
                trial_days=-1,
                revenuecat_id="rc_init_purchase",
            )
            assert user.subscription_active is False

            payload = self._make_payload(
                "INITIAL_PURCHASE", "rc_init_purchase",
                event_id="evt-init",
                product_id="dawnotemu_monthly",
                store="APP_STORE",
                expiration_days=30,
            )
            success, _, status = SubscriptionController.handle_revenuecat_webhook(payload)

            assert status == 200
            db.session.refresh(user)
            assert user.subscription_active is True
            assert user.subscription_will_renew is True
            assert user.subscription_plan == "dawnotemu_monthly"
            assert user.subscription_source == "app_store"
            assert user.subscription_expires_at is not None

    def test_expiration_deactivates_subscription(self, app):
        """EXPIRATION must set subscription_active and will_renew to False."""
        with app.app_context():
            user = _create_user(
                "expiration@example.com",
                trial_days=-1,
                subscription_active=True,
                subscription_plan="dawnotemu_monthly",
                subscription_will_renew=True,
                revenuecat_id="rc_expiration",
            )
            assert user.subscription_active is True

            payload = self._make_payload(
                "EXPIRATION", "rc_expiration",
                event_id="evt-expire",
            )
            success, _, status = SubscriptionController.handle_revenuecat_webhook(payload)

            assert status == 200
            db.session.refresh(user)
            assert user.subscription_active is False
            assert user.subscription_will_renew is False

    def test_missing_event_id_returns_400(self, app):
        """Payload with no event.id must return 400."""
        with app.app_context():
            payload = {
                "api_version": "1.0",
                "event": {
                    "type": "INITIAL_PURCHASE",
                    "id": "",
                    "app_user_id": "rc_nobody",
                    "product_id": "dawnotemu_monthly",
                    "store": "APP_STORE",
                },
            }
            success, data, status = SubscriptionController.handle_revenuecat_webhook(payload)
            assert success is False
            assert status == 400

    def test_missing_event_object_returns_400(self, app):
        """Payload without event key must return 400."""
        with app.app_context():
            payload = {"api_version": "1.0"}
            success, data, status = SubscriptionController.handle_revenuecat_webhook(payload)
            assert success is False
            assert status == 400

    def test_initial_purchase_without_expiration_uses_fallback(self, app):
        """Missing expiration_at_ms should use 35-day fallback, not None."""
        with app.app_context():
            user = _create_user(
                "no-exp-init@example.com",
                trial_days=-1,
                revenuecat_id="rc_no_exp_init",
            )
            payload = {
                "api_version": "1.0",
                "event": {
                    "type": "INITIAL_PURCHASE",
                    "id": "evt-no-exp-init",
                    "app_user_id": "rc_no_exp_init",
                    "product_id": "dawnotemu_monthly",
                    "store": "APP_STORE",
                },
            }
            success, _, status = SubscriptionController.handle_revenuecat_webhook(payload)
            assert status == 200
            db.session.refresh(user)
            assert user.subscription_active is True
            assert user.subscription_expires_at is not None
            # Fallback should be ~35 days from now
            delta = user.subscription_expires_at - datetime.utcnow()
            assert 34 <= delta.days <= 35

    def test_renewal_without_expiration_uses_fallback(self, app):
        """Missing expiration_at_ms on RENEWAL should use 35-day fallback."""
        with app.app_context():
            user = _create_user(
                "no-exp-renew@example.com",
                trial_days=-1,
                subscription_active=True,
                revenuecat_id="rc_no_exp_renew",
            )
            payload = {
                "api_version": "1.0",
                "event": {
                    "type": "RENEWAL",
                    "id": "evt-no-exp-renew",
                    "app_user_id": "rc_no_exp_renew",
                    "product_id": "dawnotemu_monthly",
                    "store": "APP_STORE",
                },
            }
            success, _, status = SubscriptionController.handle_revenuecat_webhook(payload)
            assert status == 200
            db.session.refresh(user)
            assert user.subscription_expires_at is not None
            delta = user.subscription_expires_at - datetime.utcnow()
            assert 34 <= delta.days <= 35

    def test_product_change_no_product_identifier(self, app):
        """PRODUCT_CHANGE with no product should not update subscription_plan."""
        with app.app_context():
            user = _create_user(
                "prodchange-noprod@example.com",
                subscription_active=True,
                subscription_plan="dawnotemu_monthly",
                revenuecat_id="rc_prodchange_noprod",
            )
            payload = {
                "api_version": "1.0",
                "event": {
                    "type": "PRODUCT_CHANGE",
                    "id": "evt-prodchange-noprod",
                    "app_user_id": "rc_prodchange_noprod",
                    "store": "APP_STORE",
                },
            }
            success, _, status = SubscriptionController.handle_revenuecat_webhook(payload)
            assert status == 200
            db.session.refresh(user)
            assert user.subscription_plan == "dawnotemu_monthly"

    def test_uncancellation_clears_billing_issue(self, app):
        """UNCANCELLATION should clear billing_issue_at."""
        with app.app_context():
            user = _create_user(
                "uncancel-billing@example.com",
                subscription_active=True,
                subscription_will_renew=False,
                revenuecat_id="rc_uncancel_billing",
            )
            user.billing_issue_at = datetime.utcnow()
            db.session.commit()

            payload = self._make_payload("UNCANCELLATION", "rc_uncancel_billing", event_id="evt-uncancel-billing")
            success, _, status = SubscriptionController.handle_revenuecat_webhook(payload)

            assert status == 200
            db.session.refresh(user)
            assert user.billing_issue_at is None
            assert user.subscription_will_renew is True

    def test_billing_issue_records_timestamp(self, app):
        """BILLING_ISSUE must set billing_issue_at to a timestamp."""
        with app.app_context():
            user = _create_user(
                "billing-issue@example.com",
                trial_days=-1,
                subscription_active=True,
                revenuecat_id="rc_billing_issue",
            )
            assert user.billing_issue_at is None

            payload = self._make_payload(
                "BILLING_ISSUE", "rc_billing_issue",
                event_id="evt-billing",
            )
            success, _, status = SubscriptionController.handle_revenuecat_webhook(payload)

            assert status == 200
            db.session.refresh(user)
            assert user.billing_issue_at is not None
            assert isinstance(user.billing_issue_at, datetime)
