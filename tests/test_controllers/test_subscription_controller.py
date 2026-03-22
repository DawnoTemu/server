from datetime import datetime, timedelta

from database import db
from models.user_model import User
from controllers.subscription_controller import SubscriptionController


def _create_user(email="sub-ctrl@example.com", trial_days=14,
                 subscription_active=False, subscription_plan=None,
                 subscription_will_renew=False):
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
