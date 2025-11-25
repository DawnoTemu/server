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
        assert summary["balance_cached"] == 99
        assert summary["balance_computed"] == 10
        assert summary["balance"] == 10

        db.session.delete(lot)
        db.session.delete(user)
        db.session.commit()

