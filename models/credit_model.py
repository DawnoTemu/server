from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Tuple, Optional

from sqlalchemy import and_, or_, func, select
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import db
from models.user_model import User


class CreditTransaction(db.Model):
    __tablename__ = 'credit_transactions'

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), index=True)
    amount: Mapped[int] = mapped_column(db.Integer, nullable=False)  # signed; negative for debits
    type: Mapped[str] = mapped_column(db.String(20), nullable=False)  # debit|credit|refund|expire
    reason: Mapped[Optional[str]] = mapped_column(db.String(255))
    audio_story_id: Mapped[Optional[int]] = mapped_column(db.Integer, db.ForeignKey('audio_stories.id', ondelete='SET NULL'), index=True)
    story_id: Mapped[Optional[int]] = mapped_column(db.Integer, db.ForeignKey('stories.id', ondelete='SET NULL'), index=True)
    status: Mapped[str] = mapped_column(db.String(20), nullable=False, default='applied')
    metadata_json: Mapped[Optional[dict]] = mapped_column('metadata', db.JSON)
    created_at: Mapped[datetime] = mapped_column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    allocations = relationship('CreditTransactionAllocation', back_populates='transaction', cascade="all, delete-orphan")


class CreditLot(db.Model):
    __tablename__ = 'credit_lots'

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), index=True)
    source: Mapped[str] = mapped_column(db.String(20), nullable=False)  # monthly|add_on|free|event|referral
    amount_granted: Mapped[int] = mapped_column(db.Integer, nullable=False)
    amount_remaining: Mapped[int] = mapped_column(db.Integer, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(db.DateTime)
    created_at: Mapped[datetime] = mapped_column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    allocations = relationship('CreditTransactionAllocation', back_populates='lot', cascade="all, delete-orphan")


class CreditTransactionAllocation(db.Model):
    __tablename__ = 'credit_transaction_allocations'

    transaction_id: Mapped[int] = mapped_column(db.Integer, db.ForeignKey('credit_transactions.id', ondelete='CASCADE'), primary_key=True)
    lot_id: Mapped[int] = mapped_column(db.Integer, db.ForeignKey('credit_lots.id', ondelete='CASCADE'), primary_key=True)
    amount: Mapped[int] = mapped_column(db.Integer, nullable=False)  # signed; negative for debits; positive for refunds

    transaction = relationship('CreditTransaction', back_populates='allocations')
    lot = relationship('CreditLot', back_populates='allocations')


class InsufficientCreditsError(Exception):
    pass


def _active_lots_query(user_id: int):
    now = datetime.utcnow()
    return (
        db.session.query(CreditLot)
        .filter(
            CreditLot.user_id == user_id,
            CreditLot.amount_remaining > 0,
            or_(CreditLot.expires_at.is_(None), CreditLot.expires_at > now),
        )
    )


def _priority_sources() -> List[str]:
    from utils.credits import get_credit_sources_priority

    return get_credit_sources_priority()


def _lock_user(user_id: int) -> User:
    """Fetch the user row, using FOR UPDATE when supported.

    SQLite does not support SELECT ... FOR UPDATE; in that case we fall back
    to a plain SELECT so dev/test remains functional. On Postgres and others,
    we keep row-level locking to prevent races.
    """
    bind = db.session.get_bind()
    dialect = bind.dialect.name if bind is not None else None
    stmt = select(User).where(User.id == user_id)
    if dialect not in ("sqlite", None):
        stmt = stmt.with_for_update()
    user = db.session.execute(stmt).scalar_one()
    return user


def grant(user_id: int, amount: int, reason: str, source: str, expires_at: Optional[datetime] = None):
    if amount <= 0:
        raise ValueError("Grant amount must be positive")

    user = _lock_user(user_id)

    lot = CreditLot(
        user_id=user_id,
        source=(source or '').strip().lower(),
        amount_granted=amount,
        amount_remaining=amount,
        expires_at=expires_at,
    )
    db.session.add(lot)

    tx = CreditTransaction(
        user_id=user_id,
        amount=amount,  # positive for credit/grant
        type='credit',
        reason=reason,
        story_id=None,
        audio_story_id=None,
        status='applied',
    )
    db.session.add(tx)

    # Adjust cached balance
    user.credits_balance = int(user.credits_balance or 0) + amount

    db.session.commit()
    return True, tx


def debit(user_id: int, amount: int, reason: str, audio_story_id: Optional[int] = None, story_id: Optional[int] = None):
    if amount <= 0:
        raise ValueError("Debit amount must be positive")

    # Idempotency: if a debit for this audio already exists, return it
    if audio_story_id is not None:
        existing = (
            db.session.query(CreditTransaction)
            .filter(
                CreditTransaction.audio_story_id == audio_story_id,
                CreditTransaction.user_id == user_id,
                CreditTransaction.type == 'debit',
                CreditTransaction.status == 'applied',
            )
            .order_by(CreditTransaction.created_at.desc())
            .first()
        )
        if existing:
            # Calculate outstanding amount on the existing debit
            refunded_amount = (
                db.session.query(func.coalesce(func.sum(CreditTransaction.amount), 0))
                .filter(
                    CreditTransaction.audio_story_id == audio_story_id,
                    CreditTransaction.user_id == user_id,
                    CreditTransaction.type == 'refund',
                    CreditTransaction.created_at >= existing.created_at,
                )
                .scalar()
            )
            outstanding = (-existing.amount) - refunded_amount
            if amount <= outstanding:
                # Existing debit already covers the requested amount.
                # Commit to persist any upstream changes (e.g., AudioStory status/credits_charged).
                db.session.commit()
                return True, existing
            # Need to charge the difference on top of existing debit
            extra_needed = amount - outstanding
            user = _lock_user(user_id)
            # Build available lots
            active_lots = _active_lots_query(user_id).all()
            lots_by_source: dict[str, list[CreditLot]] = {}
            for lot in active_lots:
                key = (lot.source or '').strip().lower()
                lots_by_source.setdefault(key, []).append(lot)
            for src in list(lots_by_source.keys()):
                lots_by_source[src].sort(key=lambda l: (l.expires_at or datetime.max, l.created_at))
            total_available = sum(l.amount_remaining for lots in lots_by_source.values() for l in lots)
            if total_available < extra_needed:
                raise InsufficientCreditsError(
                    f"Insufficient Story Points: need +{extra_needed}, available {total_available}"
                )
            # Order sources
            prio = _priority_sources()
            seen: set[str] = set()
            ordered_sources: list[str] = []
            for s in prio:
                if s in lots_by_source and s not in seen:
                    ordered_sources.append(s)
                    seen.add(s)
            for s in lots_by_source.keys():
                if s not in seen:
                    ordered_sources.append(s)
            remaining_extra = extra_needed
            extra_allocations: List[Tuple[CreditLot, int]] = []
            for src in ordered_sources:
                for lot in lots_by_source.get(src, []):
                    if remaining_extra <= 0:
                        break
                    take = min(remaining_extra, lot.amount_remaining)
                    if take > 0:
                        lot.amount_remaining -= take
                        extra_allocations.append((lot, take))
                        remaining_extra -= take
                if remaining_extra <= 0:
                    break
            if remaining_extra > 0:
                raise InsufficientCreditsError(
                    f"Insufficient Story Points after allocation: need +{extra_needed}, allocated {extra_needed - remaining_extra}"
                )
            # Update existing debit to include the extra charge
            existing.amount -= extra_needed  # more negative
            db.session.flush()
            # Merge allocations into existing rows to avoid PK conflicts
            existing_alloc_rows = {
                a.lot_id: a
                for a in db.session.query(CreditTransactionAllocation)
                .filter(CreditTransactionAllocation.transaction_id == existing.id)
                .all()
            }
            for lot, take in extra_allocations:
                if lot.id in existing_alloc_rows:
                    existing_alloc_rows[lot.id].amount += -take
                else:
                    db.session.add(
                        CreditTransactionAllocation(transaction_id=existing.id, lot_id=lot.id, amount=-take)
                    )
            user.credits_balance = int(user.credits_balance or 0) - extra_needed
            db.session.commit()
            return True, existing

    user = _lock_user(user_id)

    # Gather active lots and order by configured priority and soonest expiry
    active_lots = _active_lots_query(user_id).all()
    lots_by_source: dict[str, list[CreditLot]] = {}
    for lot in active_lots:
        key = (lot.source or '').strip().lower()
        lots_by_source.setdefault(key, []).append(lot)

    # Sort each source by (expires_at asc, created_at asc)
    for src in list(lots_by_source.keys()):
        lots_by_source[src].sort(key=lambda l: (l.expires_at or datetime.max, l.created_at))

    total_available = sum(l.amount_remaining for lots in lots_by_source.values() for l in lots)
    if total_available < amount:
        raise InsufficientCreditsError(f"Insufficient Story Points: need {amount}, available {total_available}")

    remaining = amount
    allocations: List[Tuple[CreditLot, int]] = []
    # Build final ordered source list: configured priority first, then any remaining sources
    prio = _priority_sources()
    seen: set[str] = set()
    ordered_sources: list[str] = []
    for s in prio:
        if s in lots_by_source and s not in seen:
            ordered_sources.append(s)
            seen.add(s)
    for s in lots_by_source.keys():
        if s not in seen:
            ordered_sources.append(s)

    for src in ordered_sources:
        for lot in lots_by_source.get(src, []):
            if remaining <= 0:
                break
            take = min(remaining, lot.amount_remaining)
            if take > 0:
                lot.amount_remaining -= take
                allocations.append((lot, take))
                remaining -= take
        if remaining <= 0:
            break

    if remaining > 0:
        # Allocation failed to satisfy requested amount; do not create a debit
        raise InsufficientCreditsError(
            f"Insufficient Story Points after allocation: need {amount}, allocated {amount - remaining}"
        )

    # Create the debit transaction (negative amount)
    tx = CreditTransaction(
        user_id=user_id,
        amount=-amount,
        type='debit',
        reason=reason,
        audio_story_id=audio_story_id,
        story_id=story_id,
        status='applied',
    )
    db.session.add(tx)
    db.session.flush()  # get tx.id for allocations

    for lot, take in allocations:
        db.session.add(
            CreditTransactionAllocation(transaction_id=tx.id, lot_id=lot.id, amount=-take)
        )

    # Adjust cached balance
    user.credits_balance = int(user.credits_balance or 0) - amount

    db.session.commit()
    return True, tx


def refund_by_audio(audio_story_id: int, reason: str):
    """Refund the currently applied debit for a given audio story.

    Selects the debit with status='applied' for the correct user and refunds
    any outstanding portion, supporting idempotent retries.
    """
    # Determine the user from the audio story to avoid cross-user refunds
    from models.audio_model import AudioStory
    audio_row = db.session.get(AudioStory, audio_story_id)
    if not audio_row:
        return True, None

    # Find the outstanding (applied) debit for this user/audio
    debit_tx = (
        db.session.query(CreditTransaction)
        .filter(
            CreditTransaction.audio_story_id == audio_story_id,
            CreditTransaction.user_id == audio_row.user_id,
            CreditTransaction.type == 'debit',
            CreditTransaction.status == 'applied',
        )
        .order_by(CreditTransaction.created_at.desc())
        .first()
    )
    if not debit_tx:
        # Nothing to refund (idempotent)
        return True, None

    user = _lock_user(debit_tx.user_id)

    # Compute how much of this specific debit has been refunded already
    refunded_amount = (
        db.session.query(func.coalesce(func.sum(CreditTransaction.amount), 0))
        .filter(
            CreditTransaction.audio_story_id == audio_story_id,
            CreditTransaction.user_id == user.id,
            CreditTransaction.type == 'refund',
            CreditTransaction.created_at >= debit_tx.created_at,
        )
        .scalar()
    )
    debit_amount = -debit_tx.amount  # positive value
    if refunded_amount >= debit_amount:
        return True, None

    to_refund = debit_amount - refunded_amount

    # Create refund transaction (positive amount)
    refund_tx = CreditTransaction(
        user_id=debit_tx.user_id,
        amount=to_refund,
        type='refund',
        reason=reason,
        audio_story_id=audio_story_id,
        story_id=debit_tx.story_id,
        status='applied',
    )
    db.session.add(refund_tx)
    db.session.flush()

    # Restore amounts to the same lots based on original allocations
    orig_allocs: List[CreditTransactionAllocation] = (
        db.session.query(CreditTransactionAllocation)
        .filter(CreditTransactionAllocation.transaction_id == debit_tx.id)
        .all()
    )

    remaining = to_refund
    for alloc in orig_allocs:
        if remaining <= 0:
            break
        lot = db.session.get(CreditLot, alloc.lot_id)
        take = min(-alloc.amount, remaining)  # alloc.amount is negative for debit
        lot.amount_remaining += take
        db.session.add(
            CreditTransactionAllocation(transaction_id=refund_tx.id, lot_id=lot.id, amount=take)
        )
        remaining -= take

    # If fully refunded, mark the original debit as refunded to allow re-debit later
    if refunded_amount + to_refund >= debit_amount:
        debit_tx.status = 'refunded'

    # Adjust cached balance
    user.credits_balance = int(user.credits_balance or 0) + to_refund

    db.session.commit()
    return True, refund_tx
