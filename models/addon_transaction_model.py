from datetime import datetime

from database import db


class ConsumedAddonTransaction(db.Model):
    """Tracks consumed add-on credit pack purchases to prevent double-grants.

    The receipt_token (RevenueCat transactionIdentifier) serves as the
    idempotency key.  Rows are append-only and never modified.
    """

    __tablename__ = 'consumed_addon_transactions'
    __table_args__ = (
        db.CheckConstraint('credits_granted > 0', name='ck_addon_credits_positive'),
        db.CheckConstraint("platform IN ('ios', 'android')", name='ck_addon_valid_platform'),
    )

    id = db.Column(db.Integer, primary_key=True)
    receipt_token = db.Column(db.String(512), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    product_id = db.Column(db.String(100), nullable=False)
    platform = db.Column(db.String(20), nullable=False)
    credits_granted = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
