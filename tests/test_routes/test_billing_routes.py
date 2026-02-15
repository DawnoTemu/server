from datetime import datetime, timedelta

import pytest

from controllers.auth_controller import AuthController
from database import db
from models.credit_model import CreditLot, CreditTransaction
from models.user_model import User


def _create_active_user(app, email="credits-user@example.com", password="CurrentPass1!"):
    with app.app_context():
        existing = User.query.filter_by(email=email).first()
        if existing:
            db.session.delete(existing)
            db.session.commit()

        user = User(
            email=email,
            is_active=True,
            email_confirmed=True,
            credits_balance=25,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        access_token = AuthController.generate_access_token(user)
        return user.id, access_token


def _cleanup_user(app, user_id):
    with app.app_context():
        user = User.query.get(user_id)
        if user:
            db.session.delete(user)
            db.session.commit()


def _seed_credit_data(app, user_id):
    """Create sample lots and transactions for the tests."""
    with app.app_context():
        now = datetime.utcnow()
        lot_active = CreditLot(
            user_id=user_id,
            source="monthly",
            amount_granted=20,
            amount_remaining=12,
            expires_at=now + timedelta(days=10),
            created_at=now - timedelta(days=5),
        )
        lot_expired = CreditLot(
            user_id=user_id,
            source="event",
            amount_granted=10,
            amount_remaining=0,
            expires_at=now - timedelta(days=1),
            created_at=now - timedelta(days=30),
        )
        db.session.add_all([lot_active, lot_expired])

        tx_credit = CreditTransaction(
            user_id=user_id,
            amount=10,
            type="credit",
            reason="monthly_grant",
            status="applied",
            metadata_json={"source": "monthly"},
            created_at=now - timedelta(days=3),
        )
        tx_debit = CreditTransaction(
            user_id=user_id,
            amount=-5,
            type="debit",
            reason="audio_synthesis:1",
            status="applied",
            created_at=now - timedelta(days=2),
        )
        tx_refund = CreditTransaction(
            user_id=user_id,
            amount=2,
            type="refund",
            reason="synthesis_failed",
            status="applied",
            created_at=now - timedelta(days=1),
        )
        db.session.add_all([tx_credit, tx_debit, tx_refund])

        user = User.query.get(user_id)
        user.credits_balance = 27  # 25 + credit(10) - debit(5) + refund(2)
        db.session.commit()


def test_get_credit_summary_with_history(client, app):
    user_id, token = _create_active_user(app)
    _seed_credit_data(app, user_id)

    response = client.get(
        "/me/credits?history_limit=2",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.get_json()

    assert data["balance"] == 12  # Computed from active lot (amount_remaining=12), not cached value
    assert data["unit_label"]
    assert data["unit_size"]
    assert len(data["lots"]) == 2
    active_lot = next(lot for lot in data["lots"] if lot["is_active"] is True)
    assert active_lot["source"] == "monthly"
    assert data["history"]["limit"] == 2
    assert len(data["history"]["items"]) == 2
    assert data["recent_transactions"] == data["history"]["items"]

    _cleanup_user(app, user_id)


def test_get_credit_history_pagination_and_filter(client, app):
    user_id, token = _create_active_user(app, email="credits-history@example.com")
    _seed_credit_data(app, user_id)

    # First page
    response = client.get(
        "/me/credits/history?limit=2",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["limit"] == 2
    assert data["offset"] == 0
    assert data["total"] == 3
    assert len(data["items"]) == 2
    assert data["next_offset"] == 2

    # Second page
    response = client.get(
        "/me/credits/history?limit=2&offset=2",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["offset"] == 2
    assert len(data["items"]) == 1
    assert data["next_offset"] is None

    # Filter by type
    response = client.get(
        "/me/credits/history?type=credit",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert all(entry["type"] == "credit" for entry in data["items"])
    assert data["applied_types"] == ["credit"]

    _cleanup_user(app, user_id)
