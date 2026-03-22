from datetime import datetime, timedelta

from database import db
from models.user_model import User
from models.credit_model import grant as credit_grant
from controllers.addon_controller import AddonController


def _create_subscribed_user(email="addon-ctrl@example.com", credits=0):
    user = User(
        email=email,
        is_active=True,
        email_confirmed=True,
        credits_balance=0,
        trial_expires_at=datetime.utcnow() - timedelta(days=1),
        subscription_active=True,
        subscription_plan="monthly",
    )
    user.set_password("TestPass123!")
    db.session.add(user)
    db.session.commit()

    if credits > 0:
        credit_grant(user.id, credits, reason="test_seed", source="free")
        db.session.refresh(user)

    return user


def _create_non_subscriber(email="nonsub@example.com"):
    user = User(
        email=email,
        is_active=True,
        email_confirmed=True,
        credits_balance=0,
        subscription_active=False,
    )
    user.set_password("TestPass123!")
    db.session.add(user)
    db.session.commit()
    return user


class TestAddonController:

    def test_grant_addon_success(self, app):
        with app.app_context():
            user = _create_subscribed_user("grant-ok@example.com", credits=10)
            success, data, status = AddonController.grant_addon(
                user, "rc_abc123", "credits_10", "ios",
            )

            assert success is True
            assert status == 200
            assert data["credits_granted"] == 10
            assert data["new_balance"] == 20

    def test_grant_addon_idempotent_replay(self, app):
        with app.app_context():
            user = _create_subscribed_user("idem@example.com", credits=10)

            AddonController.grant_addon(user, "rc_idem", "credits_10", "ios")
            db.session.refresh(user)

            success, data, status = AddonController.grant_addon(
                user, "rc_idem", "credits_10", "ios",
            )

            assert success is True
            assert status == 200
            assert data["credits_granted"] == 10
            assert data["new_balance"] == 20

    def test_grant_addon_cross_user_conflict(self, app):
        with app.app_context():
            user_a = _create_subscribed_user("cross-a@example.com", credits=10)
            user_b = _create_subscribed_user("cross-b@example.com", credits=10)

            AddonController.grant_addon(user_a, "rc_cross", "credits_10", "ios")

            success, data, status = AddonController.grant_addon(
                user_b, "rc_cross", "credits_10", "ios",
            )

            assert success is False
            assert status == 409

    def test_grant_addon_invalid_product(self, app):
        with app.app_context():
            user = _create_subscribed_user("badprod@example.com")
            success, data, status = AddonController.grant_addon(
                user, "rc_bad", "credits_999", "ios",
            )

            assert success is False
            assert status == 400

    def test_grant_addon_non_subscriber(self, app):
        with app.app_context():
            user = _create_non_subscriber("nonsub-addon@example.com")
            success, data, status = AddonController.grant_addon(
                user, "rc_nosub", "credits_10", "ios",
            )

            assert success is False
            assert status == 403

    def test_grant_addon_invalid_platform(self, app):
        with app.app_context():
            user = _create_subscribed_user("badplat@example.com")
            success, data, status = AddonController.grant_addon(
                user, "rc_plat", "credits_10", "web",
            )

            assert success is False
            assert status == 400
