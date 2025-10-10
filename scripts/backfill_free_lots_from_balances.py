#!/usr/bin/env python3
"""
Backfill free credit lots to reconcile users' cached balances.

Usage:
  python scripts/backfill_free_lots_from_balances.py --apply [--user-id 123]

Behavior:
- For each (or selected) user, computes delta = credits_balance - sum(amount_remaining of non-expired lots).
- If delta > 0, creates a non-expiring 'free' credit lot with amount_granted = amount_remaining = delta.
- Does not modify credits_balance; it already represents the intended total.
"""

import argparse
import os
import sys
from datetime import datetime

# Ensure project root is on sys.path for 'import app'
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app import app as flask_app
from database import db
from models.user_model import User
from models.credit_model import CreditLot


def compute_delta(user: User) -> int:
    now = datetime.utcnow()
    lots = (
        db.session.query(CreditLot)
        .filter(
            CreditLot.user_id == user.id,
            (CreditLot.expires_at.is_(None) | (CreditLot.expires_at > now)),
        )
        .all()
    )
    remaining_sum = sum(int(l.amount_remaining or 0) for l in lots)
    bal = int(user.credits_balance or 0)
    return max(0, bal - remaining_sum)


def backfill(user: User, delta: int, apply: bool) -> None:
    if delta <= 0:
        return
    if apply:
        lot = CreditLot(
            user_id=user.id,
            source='free',
            amount_granted=delta,
            amount_remaining=delta,
            expires_at=None,
        )
        db.session.add(lot)
    print(f"user_id={user.id} email={user.email} delta={delta} action={'CREATE_LOT' if apply else 'DRY_RUN'}")


def main():
    parser = argparse.ArgumentParser(description='Backfill free lots for existing balances')
    parser.add_argument('--apply', action='store_true', help='Apply changes (default is dry-run)')
    parser.add_argument('--user-id', type=int, help='Process only a single user id')
    args = parser.parse_args()

    with flask_app.app_context():
        q = User.query
        if args.user_id:
            q = q.filter(User.id == args.user_id)
        users = q.all()
        total_delta = 0
        for u in users:
            delta = compute_delta(u)
            if delta > 0:
                total_delta += delta
                backfill(u, delta, args.apply)
        if args.apply:
            db.session.commit()
        print(f"Completed. Users affected: {sum(1 for u in users if compute_delta(u) > 0)} total_delta={total_delta}")


if __name__ == '__main__':
    main()
