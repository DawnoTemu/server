from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from database import db
from models.user_model import User
from models.credit_model import grant as credit_grant
from controllers.addon_controller import (
    AddonController,
    ReceiptValidationUnavailable,
    _validate_receipt_with_revenuecat,
)


def _create_subscribed_user(email="addon-ctrl@example.com", credits=0):
    user = User(
        email=email,
        is_active=True,
        email_confirmed=True,
        credits_balance=0,
        trial_expires_at=datetime.utcnow() - timedelta(days=1),
        subscription_active=True,
        subscription_plan="monthly",
        subscription_expires_at=datetime.utcnow() + timedelta(days=30),
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

    @patch("controllers.addon_controller._validate_receipt_with_revenuecat", return_value=True)
    def test_grant_addon_success(self, mock_validate, app):
        with app.app_context():
            user = _create_subscribed_user("grant-ok@example.com", credits=10)
            success, data, status = AddonController.grant_addon(
                user, "rc_abc123", "credits_10", "ios",
            )

            assert success is True
            assert status == 200
            assert data["credits_granted"] == 10
            assert data["new_balance"] == 20
            mock_validate.assert_called_once()

    @patch("controllers.addon_controller._validate_receipt_with_revenuecat", return_value=True)
    def test_grant_addon_idempotent_replay(self, mock_validate, app):
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

    @patch("controllers.addon_controller._validate_receipt_with_revenuecat", return_value=True)
    def test_grant_addon_cross_user_conflict(self, mock_validate, app):
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

    def test_grant_addon_expired_subscription(self, app):
        """Subscription with expired date should be rejected even if bool is True."""
        with app.app_context():
            user = User(
                email="expired-sub-addon@example.com",
                is_active=True,
                email_confirmed=True,
                credits_balance=0,
                subscription_active=True,
                subscription_plan="monthly",
                subscription_expires_at=datetime.utcnow() - timedelta(days=1),
            )
            user.set_password("TestPass123!")
            db.session.add(user)
            db.session.commit()

            success, data, status = AddonController.grant_addon(
                user, "rc_exp", "credits_10", "ios",
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

    @patch("controllers.addon_controller._validate_receipt_with_revenuecat", return_value=False)
    def test_grant_addon_receipt_validation_failure(self, mock_validate, app):
        with app.app_context():
            user = _create_subscribed_user("bad-receipt@example.com", credits=10)
            success, data, status = AddonController.grant_addon(
                user, "rc_fake_receipt", "credits_10", "ios",
            )

            assert success is False
            assert status == 403
            assert "validation" in data["error"].lower()

    @patch("controllers.addon_controller._validate_receipt_with_revenuecat", return_value=True)
    @patch("controllers.addon_controller.credit_grant", side_effect=RuntimeError("db error"))
    def test_grant_addon_generic_exception_returns_500(self, mock_grant, mock_validate, app):
        with app.app_context():
            user = _create_subscribed_user("generic-exc@example.com", credits=10)
            success, data, status = AddonController.grant_addon(
                user, "rc_generic_exc", "credits_10", "ios",
            )

            assert success is False
            assert status == 500

    @patch(
        "controllers.addon_controller._validate_receipt_with_revenuecat",
        side_effect=ReceiptValidationUnavailable("service down"),
    )
    def test_grant_addon_transient_error_returns_503(self, mock_validate, app):
        with app.app_context():
            user = _create_subscribed_user("transient@example.com", credits=10)
            success, data, status = AddonController.grant_addon(
                user, "rc_transient", "credits_10", "ios",
            )

            assert success is False
            assert status == 503
            assert "retry" in data["error"].lower()

    @patch(
        "controllers.addon_controller._validate_receipt_with_revenuecat",
        side_effect=ValueError("unexpected parse error"),
    )
    def test_grant_addon_unexpected_validation_error_returns_500(self, mock_validate, app):
        with app.app_context():
            user = _create_subscribed_user("unexpected-err@example.com", credits=10)
            success, data, status = AddonController.grant_addon(
                user, "rc_unexpected", "credits_10", "ios",
            )

            assert success is False
            assert status == 500


def _v1_response(non_subscriptions):
    """Build a fake RevenueCat v1 /v1/subscribers response."""
    return MagicMock(
        status_code=200,
        json=lambda: {
            "subscriber": {
                "non_subscriptions": non_subscriptions,
            }
        },
    )


class TestValidateReceiptWithRevenueCat:
    """The validator talks to the RevenueCat v1 API (see addon_controller).

    Why v1: the mobile SDK's ``nonSubscriptionTransactions[i].transactionIdentifier``
    field returns the v1-format internal id (e.g. ``o1_kSFvmriDAHzQ1wdJi0UAhg``),
    which the v2 API does not expose as any field. Matching against v2 always
    failed in production. These tests mock the v1 response shape.
    """

    def test_returns_true_when_api_key_missing_in_dev(self, app):
        with app.app_context():
            user = _create_subscribed_user("val-dev@example.com")
            user.revenuecat_app_user_id = "rc_dev"
            with patch("controllers.addon_controller.Config.REVENUECAT_IOS_PUBLIC_KEY", None), \
                 patch("controllers.addon_controller.os.getenv", return_value="development"):
                result = _validate_receipt_with_revenuecat(user, "tok_123", "credits_10", "ios")
            assert result is True

    def test_returns_false_when_api_key_missing_and_env_unknown(self, app):
        """Ambiguous environment (no FLASK_ENV/ENVIRONMENT) must reject."""
        with app.app_context():
            user = _create_subscribed_user("val-ambiguous@example.com")
            user.revenuecat_app_user_id = "rc_ambiguous"
            with patch("controllers.addon_controller.Config.REVENUECAT_IOS_PUBLIC_KEY", None), \
                 patch("controllers.addon_controller.os.getenv", return_value=""):
                result = _validate_receipt_with_revenuecat(user, "tok_123", "credits_10", "ios")
            assert result is False

    def test_returns_false_when_api_key_missing_in_production(self, app):
        with app.app_context():
            user = _create_subscribed_user("val-prod@example.com")
            user.revenuecat_app_user_id = "rc_prod"
            with patch("controllers.addon_controller.Config.REVENUECAT_IOS_PUBLIC_KEY", None), \
                 patch("controllers.addon_controller.os.getenv", return_value="production"):
                result = _validate_receipt_with_revenuecat(user, "tok_123", "credits_10", "ios")
            assert result is False

    def test_returns_false_for_unknown_platform(self, app):
        with app.app_context():
            user = _create_subscribed_user("val-unknown-plat@example.com")
            user.revenuecat_app_user_id = "rc_unknown"
            result = _validate_receipt_with_revenuecat(user, "tok_123", "credits_10", "web")
            assert result is False

    @patch("controllers.addon_controller.Config.REVENUECAT_IOS_PUBLIC_KEY", "test-ios-key")
    def test_returns_false_when_no_rc_user_id(self, app):
        with app.app_context():
            user = _create_subscribed_user("val-norc@example.com")
            # user has no revenuecat_app_user_id set
            result = _validate_receipt_with_revenuecat(user, "tok_123", "credits_10", "ios")
            assert result is False

    @patch("controllers.addon_controller.requests.get")
    @patch("controllers.addon_controller.Config.REVENUECAT_IOS_PUBLIC_KEY", "test-ios-key")
    def test_returns_true_when_receipt_matches_by_v1_id(self, mock_get, app):
        """Mobile SDK sends v1-format id; server should match on it."""
        with app.app_context():
            user = _create_subscribed_user("val-match-v1@example.com")
            user.revenuecat_app_user_id = "rc_match_v1"
            db.session.commit()
            mock_get.return_value = _v1_response({
                "credits_10": [
                    {
                        "id": "o1_kSFvmriDAHzQ1wdJi0UAhg",
                        "store_transaction_id": "2000001151372110",
                        "store": "app_store",
                        "is_sandbox": True,
                    }
                ]
            })
            result = _validate_receipt_with_revenuecat(
                user, "o1_kSFvmriDAHzQ1wdJi0UAhg", "credits_10", "ios"
            )
            assert result is True

    @patch("controllers.addon_controller.requests.get")
    @patch("controllers.addon_controller.Config.REVENUECAT_IOS_PUBLIC_KEY", "test-ios-key")
    def test_returns_true_when_receipt_matches_by_store_transaction_id(self, mock_get, app):
        """Fallback: server also matches on Apple/Google store_transaction_id."""
        with app.app_context():
            user = _create_subscribed_user("val-match-store@example.com")
            user.revenuecat_app_user_id = "rc_match_store"
            db.session.commit()
            mock_get.return_value = _v1_response({
                "credits_10": [
                    {
                        "id": "o1_differentv1id",
                        "store_transaction_id": "2000001151372110",
                        "store": "app_store",
                    }
                ]
            })
            result = _validate_receipt_with_revenuecat(
                user, "2000001151372110", "credits_10", "ios"
            )
            assert result is True

    @patch("controllers.addon_controller.requests.get")
    @patch("controllers.addon_controller.Config.REVENUECAT_IOS_PUBLIC_KEY", "test-ios-key")
    def test_rejects_product_mismatch_billing_bypass(self, mock_get, app):
        """Regression: a valid receipt for credits_10 must NOT be redeemable as credits_30.

        With the v1 API this is enforced implicitly because transactions are
        grouped by product_id. The validator looks up ``non_subscriptions[credits_30]``
        when the client claims credits_30 — so a receipt filed under credits_10
        is simply not there.
        """
        with app.app_context():
            user = _create_subscribed_user("val-mismatch@example.com")
            user.revenuecat_app_user_id = "rc_mismatch"
            db.session.commit()
            mock_get.return_value = _v1_response({
                "credits_10": [
                    {
                        "id": "o1_cheapReceipt",
                        "store_transaction_id": "2000000000000001",
                        "store": "app_store",
                    }
                ]
                # note: no credits_30 bucket
            })
            # User paid for credits_10 but is trying to redeem as credits_30
            result = _validate_receipt_with_revenuecat(
                user, "o1_cheapReceipt", "credits_30", "ios"
            )
            assert result is False

    @patch("controllers.addon_controller.requests.get")
    @patch("controllers.addon_controller.Config.REVENUECAT_IOS_PUBLIC_KEY", "test-ios-key")
    def test_rejects_product_mismatch_when_both_products_exist(self, mock_get, app):
        """Regression: claiming credits_30 when the receipt is in credits_10 bucket."""
        with app.app_context():
            user = _create_subscribed_user("val-mismatch-both@example.com")
            user.revenuecat_app_user_id = "rc_mismatch_both"
            db.session.commit()
            mock_get.return_value = _v1_response({
                "credits_10": [
                    {"id": "o1_cheap", "store_transaction_id": "2001"},
                ],
                "credits_30": [
                    {"id": "o1_expensive", "store_transaction_id": "2002"},
                ],
            })
            # o1_cheap is under credits_10, not credits_30
            result = _validate_receipt_with_revenuecat(
                user, "o1_cheap", "credits_30", "ios"
            )
            assert result is False

    @patch("controllers.addon_controller.requests.get")
    @patch("controllers.addon_controller.Config.REVENUECAT_IOS_PUBLIC_KEY", "test-ios-key")
    def test_returns_false_when_receipt_not_found(self, mock_get, app):
        with app.app_context():
            user = _create_subscribed_user("val-nofind@example.com")
            user.revenuecat_app_user_id = "rc_nofind"
            db.session.commit()
            mock_get.return_value = _v1_response({})
            result = _validate_receipt_with_revenuecat(
                user, "tok_missing", "credits_10", "ios"
            )
            assert result is False

    @patch("controllers.addon_controller.requests.get")
    @patch("controllers.addon_controller.Config.REVENUECAT_IOS_PUBLIC_KEY", "test-ios-key")
    def test_returns_false_when_product_bucket_empty(self, mock_get, app):
        with app.app_context():
            user = _create_subscribed_user("val-empty-bucket@example.com")
            user.revenuecat_app_user_id = "rc_empty"
            db.session.commit()
            mock_get.return_value = _v1_response({"credits_10": []})
            result = _validate_receipt_with_revenuecat(
                user, "tok_anything", "credits_10", "ios"
            )
            assert result is False

    @patch("controllers.addon_controller.requests.get")
    @patch("controllers.addon_controller.Config.REVENUECAT_ANDROID_PUBLIC_KEY", "test-android-key")
    def test_android_uses_android_public_key(self, mock_get, app):
        """Android platform must select the Android public key."""
        with app.app_context():
            user = _create_subscribed_user("val-android@example.com")
            user.revenuecat_app_user_id = "rc_android"
            db.session.commit()
            mock_get.return_value = _v1_response({
                "credits_10": [
                    {"id": "GPA.3312-1234-5678-90000", "store_transaction_id": "GPA.3312-1234-5678-90000"}
                ]
            })
            result = _validate_receipt_with_revenuecat(
                user, "GPA.3312-1234-5678-90000", "credits_10", "android"
            )
            assert result is True
            # Verify the correct key was used in the Authorization header
            _args, kwargs = mock_get.call_args
            assert kwargs["headers"]["Authorization"] == "Bearer test-android-key"

    @patch("controllers.addon_controller.requests.get")
    @patch("controllers.addon_controller.Config.REVENUECAT_IOS_PUBLIC_KEY", "test-ios-key")
    def test_raises_on_timeout(self, mock_get, app):
        import requests as req
        with app.app_context():
            user = _create_subscribed_user("val-timeout@example.com")
            user.revenuecat_app_user_id = "rc_timeout"
            db.session.commit()
            mock_get.side_effect = req.exceptions.Timeout("timed out")
            import pytest
            with pytest.raises(ReceiptValidationUnavailable):
                _validate_receipt_with_revenuecat(user, "tok_timeout", "credits_10", "ios")

    @patch("controllers.addon_controller.requests.get")
    @patch("controllers.addon_controller.Config.REVENUECAT_IOS_PUBLIC_KEY", "test-ios-key")
    def test_raises_on_connection_error(self, mock_get, app):
        import requests as req
        with app.app_context():
            user = _create_subscribed_user("val-conn@example.com")
            user.revenuecat_app_user_id = "rc_conn"
            db.session.commit()
            mock_get.side_effect = req.exceptions.ConnectionError("refused")
            import pytest
            with pytest.raises(ReceiptValidationUnavailable):
                _validate_receipt_with_revenuecat(user, "tok_conn", "credits_10", "ios")

    @patch("controllers.addon_controller.requests.get")
    @patch("controllers.addon_controller.Config.REVENUECAT_IOS_PUBLIC_KEY", "test-ios-key")
    def test_raises_on_server_error(self, mock_get, app):
        """5xx from RevenueCat should raise ReceiptValidationUnavailable, not return False."""
        import pytest
        with app.app_context():
            user = _create_subscribed_user("val-http500@example.com")
            user.revenuecat_app_user_id = "rc_http500"
            db.session.commit()
            mock_get.return_value = MagicMock(
                status_code=500,
                text="Internal Server Error",
            )
            with pytest.raises(ReceiptValidationUnavailable):
                _validate_receipt_with_revenuecat(user, "tok_http", "credits_10", "ios")

    @patch("controllers.addon_controller.requests.get")
    @patch("controllers.addon_controller.Config.REVENUECAT_IOS_PUBLIC_KEY", "test-ios-key")
    def test_returns_false_on_client_error(self, mock_get, app):
        """4xx from RevenueCat should return False (genuinely not found)."""
        with app.app_context():
            user = _create_subscribed_user("val-http404@example.com")
            user.revenuecat_app_user_id = "rc_http404"
            db.session.commit()
            mock_get.return_value = MagicMock(
                status_code=404,
                text="Not Found",
            )
            result = _validate_receipt_with_revenuecat(user, "tok_http", "credits_10", "ios")
            assert result is False
