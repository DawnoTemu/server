from datetime import datetime, timedelta

from database import db
from models.credit_model import CreditLot, get_user_credit_summary
from models.user_model import User


def test_credit_summary_includes_cache_and_computed(app):
    with app.app_context():
        user = User(email="credit-mismatch@example.com", is_active=True, email_confirmed=True)
        user.set_password("Password123!")
        user.credits_balance = 99
        db.session.add(user)
        db.session.commit()

        lot = CreditLot(
            user_id=user.id,
            source="free",
            amount_granted=10,
            amount_remaining=10,
            expires_at=datetime.utcnow() + timedelta(days=1),
        )
        db.session.add(lot)
        db.session.commit()

        summary = get_user_credit_summary(user.id)
        # After reconciliation, cached balance is updated to match computed
        assert summary["balance_cached"] == 10
        assert summary["balance_computed"] == 10
        assert summary["balance"] == 10


def test_credit_summary_excludes_expired_and_reconciles_cache(app):
    with app.app_context():
        user = User(email="credit-expired@example.com", is_active=True, email_confirmed=True)
        user.set_password("Password123!")
        # Deliberately stale cached balance
        user.credits_balance = 50
        db.session.add(user)
        db.session.commit()

        now = datetime.utcnow()
        active_lot = CreditLot(
            user_id=user.id,
            source="monthly",
            amount_granted=10,
            amount_remaining=7,
            expires_at=now + timedelta(days=2),
        )
        expired_lot = CreditLot(
            user_id=user.id,
            source="event",
            amount_granted=20,
            amount_remaining=20,
            expires_at=now - timedelta(days=1),
        )
        db.session.add_all([active_lot, expired_lot])
        db.session.commit()

        summary = get_user_credit_summary(user.id)

        assert summary["balance"] == 7
        assert summary["balance_computed"] == 7
        assert summary["balance_cached"] == 7

        lots_by_source = {lot["source"]: lot for lot in summary["lots"]}
        assert lots_by_source["monthly"]["is_active"] is True
        assert lots_by_source["event"]["is_active"] is False

        refreshed = db.session.get(User, user.id)
        assert refreshed.credits_balance == 7
