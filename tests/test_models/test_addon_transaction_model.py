import pytest
from datetime import datetime

from database import db
from models.user_model import User
from models.addon_transaction_model import ConsumedAddonTransaction


def _create_user(app, email="addon-user@example.com"):
    with app.app_context():
        user = User(email=email, is_active=True, email_confirmed=True, credits_balance=0)
        user.set_password("TestPass123!")
        db.session.add(user)
        db.session.commit()
        return user.id


class TestConsumedAddonTransaction:
    def test_create_consumed_addon_transaction(self, app):
        with app.app_context():
            user_id = _create_user(app, "create-addon@example.com")
            tx = ConsumedAddonTransaction(
                receipt_token="rc_tx_abc123",
                user_id=user_id,
                product_id="credits_10",
                platform="ios",
                credits_granted=10,
            )
            db.session.add(tx)
            db.session.commit()

            fetched = ConsumedAddonTransaction.query.filter_by(receipt_token="rc_tx_abc123").first()
            assert fetched is not None
            assert fetched.user_id == user_id
            assert fetched.product_id == "credits_10"
            assert fetched.platform == "ios"
            assert fetched.credits_granted == 10
            assert fetched.created_at is not None

    def test_receipt_token_uniqueness_constraint(self, app):
        with app.app_context():
            uid1 = _create_user(app, "unique1@example.com")
            uid2 = _create_user(app, "unique2@example.com")

            tx1 = ConsumedAddonTransaction(
                receipt_token="rc_tx_unique",
                user_id=uid1,
                product_id="credits_10",
                platform="ios",
                credits_granted=10,
            )
            db.session.add(tx1)
            db.session.commit()

            tx2 = ConsumedAddonTransaction(
                receipt_token="rc_tx_unique",
                user_id=uid2,
                product_id="credits_20",
                platform="android",
                credits_granted=20,
            )
            db.session.add(tx2)
            with pytest.raises(Exception):
                db.session.commit()
            db.session.rollback()
