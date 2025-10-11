from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from models.credit_model import CreditLot, CreditTransaction, CreditTransactionAllocation
from tasks import billing_tasks


class _FakeQuery:
    def __init__(self, items):
        self._items = list(items)

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return list(self._items)


class _FakeSession:
    def __init__(self, lots, users):
        self._lots = list(lots)
        self._users = {u.id: u for u in users}
        self.added = []
        self.committed = False
        self.rollback_called = False

    def query(self, model):
        if model is CreditLot:
            return _FakeQuery(self._lots)
        raise AssertionError(f"Unexpected query for model {model}")

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rollback_called = True

    def get(self, model, obj_id):
        return self._users.get(obj_id)

    def flush(self):
        pass


def test_expire_credit_lots_records_ledger(monkeypatch):
    """Expire job should zero lots, update balances, and persist ledger rows."""
    now = datetime.utcnow()
    lot_a = CreditLot(
        user_id=1,
        source='monthly',
        amount_granted=10,
        amount_remaining=10,
        expires_at=now - timedelta(days=1),
    )
    lot_a.id = 101

    lot_b = CreditLot(
        user_id=1,
        source='promo',
        amount_granted=5,
        amount_remaining=3,
        expires_at=now - timedelta(hours=2),
    )
    lot_b.id = 102

    lot_c = CreditLot(
        user_id=2,
        source='gift',
        amount_granted=4,
        amount_remaining=4,
        expires_at=now - timedelta(minutes=30),
    )
    lot_c.id = 201

    user_one = SimpleNamespace(id=1, credits_balance=20)
    user_two = SimpleNamespace(id=2, credits_balance=2)

    fake_session = _FakeSession([lot_a, lot_b, lot_c], [user_one, user_two])
    monkeypatch.setattr(billing_tasks, 'db', SimpleNamespace(session=fake_session))

    billing_tasks.expire_credit_lots()

    assert lot_a.amount_remaining == 0
    assert lot_b.amount_remaining == 0
    assert lot_c.amount_remaining == 0

    assert user_one.credits_balance == 7  # 20 - (10 + 3)
    assert user_two.credits_balance == 0  # cannot go below zero

    assert fake_session.committed is True
    assert fake_session.rollback_called is False

    transactions = [obj for obj in fake_session.added if isinstance(obj, CreditTransaction)]
    allocations = [obj for obj in fake_session.added if isinstance(obj, CreditTransactionAllocation)]

    assert len(transactions) == 3
    assert len(allocations) == 3

    tx_by_lot = {tx.metadata_json['lot_id']: tx for tx in transactions}
    assert set(tx_by_lot.keys()) == {lot_a.id, lot_b.id, lot_c.id}

    expected_amounts = {lot_a.id: 10, lot_b.id: 3, lot_c.id: 4}
    expected_sources = {lot_a.id: 'monthly', lot_b.id: 'promo', lot_c.id: 'gift'}

    for lot_id, tx in tx_by_lot.items():
        assert tx.type == 'expire'
        assert tx.reason == 'auto_expire'
        assert tx.amount == -expected_amounts[lot_id]
        assert tx.metadata_json['lot_source'] == expected_sources[lot_id]
        assert tx.metadata_json['source_task'] == 'billing.expire_credit_lots'

    allocation_amounts = sorted(allocation.amount for allocation in allocations)
    transaction_amounts = sorted(tx.amount for tx in transactions)
    assert allocation_amounts == transaction_amounts
