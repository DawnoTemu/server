"""
Concurrent credit race condition tests.

Verifies that the SELECT FOR UPDATE locking in credit_model.debit()
prevents double-spend when multiple threads attempt to debit the same
user's credits simultaneously.

Runs against a real PostgreSQL database (via docker-compose test setup)
to exercise actual row-level locking. SQLite tests skip FOR UPDATE and
therefore cannot fully validate this behavior.

Usage:
  cd server && python -m pytest tests/test_credit_race.py -v
"""

import os
import sys
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import db
from models.user_model import User
from models.credit_model import (
    CreditLot,
    CreditTransaction,
    CreditTransactionAllocation,
    InsufficientCreditsError,
    debit,
    grant,
)
from models.audio_model import AudioStory, AudioStatus
from models.story_model import Story
from models.voice_model import Voice

logger = logging.getLogger("test_credit_race")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def race_user(app):
    """Create a user with exactly 1 credit for race condition testing."""
    with app.app_context():
        user = User(
            email="race-test@dawnotemu.test",
            is_active=True,
            email_confirmed=True,
            credits_balance=0,
        )
        user.set_password("TestPass123!")
        db.session.add(user)
        db.session.commit()

        # Grant exactly 1 credit
        grant(user.id, 1, "race_test_setup", "free")

        # Verify balance
        db.session.refresh(user)
        assert user.credits_balance == 1
        yield user


@pytest.fixture
def race_story(app):
    """Create a story for synthesis requests."""
    with app.app_context():
        story = Story(
            title="Race Test Story",
            author="Test Author",
            description="Story for credit race testing",
            content="This is a short test story for credit race testing.",
        )
        db.session.add(story)
        db.session.commit()
        yield story


@pytest.fixture
def race_voice(app, race_user):
    """Create a voice belonging to the race test user."""
    with app.app_context():
        voice = Voice(
            name="Race Test Voice",
            user_id=race_user.id,
            elevenlabs_voice_id="fake-el-voice-id-race",
            s3_sample_key="race/sample.wav",
            allocation_status="ready",
        )
        db.session.add(voice)
        db.session.commit()
        yield voice


# ---------------------------------------------------------------------------
# Helper: run debit in a thread with its own app context
# ---------------------------------------------------------------------------


def _debit_in_thread(app, user_id, amount, audio_story_id, story_id, thread_idx):
    """
    Run a credit debit inside a fresh app context.
    Returns (thread_idx, success, error_class_name).
    """
    with app.app_context():
        try:
            debit(
                user_id=user_id,
                amount=amount,
                reason=f"race_test_thread_{thread_idx}",
                audio_story_id=audio_story_id,
                story_id=story_id,
                auto_commit=True,
            )
            return (thread_idx, True, None)
        except InsufficientCreditsError:
            return (thread_idx, False, "InsufficientCreditsError")
        except Exception as exc:
            return (thread_idx, False, type(exc).__name__)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCreditRaceCondition:
    """Test concurrent credit debit operations for race conditions."""

    def test_concurrent_debit_no_double_spend(
        self, app, race_user, race_story, race_voice
    ):
        """
        10 threads simultaneously attempt to debit 1 credit from a user
        who has exactly 1 credit. Exactly 1 should succeed, 9 should fail
        with InsufficientCreditsError. No overdraft should occur.
        """
        thread_count = 10

        with app.app_context():
            # Create distinct audio_story records for each thread.
            # Each needs a unique (story_id, voice_id) pair due to the
            # uq_audio_stories_story_voice constraint, so we create
            # per-thread stories.
            audio_story_ids = []
            for i in range(thread_count):
                story = Story(
                    title=f"Race Story {i}",
                    author="Test",
                    description="race",
                    content="race test content",
                )
                db.session.add(story)
                db.session.flush()
                audio = AudioStory(
                    story_id=story.id,
                    voice_id=race_voice.id,
                    user_id=race_user.id,
                    status=AudioStatus.PENDING.value,
                )
                db.session.add(audio)
                db.session.flush()
                audio_story_ids.append(audio.id)
            db.session.commit()

        # Fire all threads simultaneously
        results = []
        with ThreadPoolExecutor(max_workers=thread_count) as executor:
            futures = {
                executor.submit(
                    _debit_in_thread,
                    app,
                    race_user.id,
                    1,  # debit 1 credit
                    audio_story_ids[i],
                    race_story.id,
                    i,
                ): i
                for i in range(thread_count)
            }
            for future in as_completed(futures):
                results.append(future.result())

        successes = [r for r in results if r[1]]
        failures = [r for r in results if not r[1]]

        # Assertions
        assert len(successes) == 1, (
            f"Expected exactly 1 successful debit, got {len(successes)}. "
            f"Results: {results}"
        )

        assert all(
            r[2] == "InsufficientCreditsError" for r in failures
        ), f"Non-InsufficientCreditsError failures: {[r for r in failures if r[2] != 'InsufficientCreditsError']}"

        # Verify final balance is exactly 0 (no overdraft)
        with app.app_context():
            user = db.session.get(User, race_user.id)
            assert user.credits_balance == 0, (
                f"Expected balance=0 after single debit, got {user.credits_balance}"
            )

        # Verify lot balances sum correctly
        with app.app_context():
            total_remaining = (
                db.session.query(db.func.coalesce(db.func.sum(CreditLot.amount_remaining), 0))
                .filter(CreditLot.user_id == race_user.id)
                .scalar()
            )
            assert total_remaining == 0, (
                f"Expected lot sum=0, got {total_remaining}"
            )

    def test_concurrent_debit_same_audio_story_idempotent(
        self, app, race_user, race_story, race_voice
    ):
        """
        Multiple threads debit for the SAME audio_story_id.
        The debit function's idempotency check should ensure only
        one actual debit occurs.
        """
        thread_count = 5

        with app.app_context():
            # Create a single audio_story record shared by all threads
            audio = AudioStory(
                story_id=race_story.id,
                voice_id=race_voice.id,
                user_id=race_user.id,
                status=AudioStatus.PENDING.value,
            )
            db.session.add(audio)
            db.session.commit()
            shared_audio_id = audio.id

        results = []
        with ThreadPoolExecutor(max_workers=thread_count) as executor:
            futures = {
                executor.submit(
                    _debit_in_thread,
                    app,
                    race_user.id,
                    1,
                    shared_audio_id,  # Same audio_story_id
                    race_story.id,
                    i,
                ): i
                for i in range(thread_count)
            }
            for future in as_completed(futures):
                results.append(future.result())

        successes = [r for r in results if r[1]]

        # All should succeed due to idempotency (reusing existing debit)
        # OR exactly one succeeds and others fail — both are acceptable
        # as long as final balance is correct
        with app.app_context():
            user = db.session.get(User, race_user.id)
            assert user.credits_balance >= 0, (
                f"Overdraft detected: balance={user.credits_balance}"
            )

            # Count actual applied debit transactions
            applied_debits = (
                CreditTransaction.query.filter(
                    CreditTransaction.audio_story_id == shared_audio_id,
                    CreditTransaction.user_id == race_user.id,
                    CreditTransaction.type == "debit",
                    CreditTransaction.status == "applied",
                ).count()
            )
            assert applied_debits == 1, (
                f"Expected exactly 1 applied debit for audio {shared_audio_id}, "
                f"got {applied_debits}"
            )

    def test_no_negative_balance(self, app, race_user, race_story, race_voice):
        """
        Grant 3 credits, fire 10 concurrent debits of 1 credit each.
        Exactly 3 should succeed. Balance must be exactly 0.
        """
        thread_count = 10

        with app.app_context():
            # Grant 2 more credits (user already has 1 from fixture)
            grant(race_user.id, 2, "extra_credits", "free")
            user = db.session.get(User, race_user.id)
            assert user.credits_balance == 3

            # Each thread needs a unique (story_id, voice_id) pair
            audio_story_ids = []
            for i in range(thread_count):
                story = Story(
                    title=f"Neg Balance Story {i}",
                    author="Test",
                    description="race",
                    content="race test content",
                )
                db.session.add(story)
                db.session.flush()
                audio = AudioStory(
                    story_id=story.id,
                    voice_id=race_voice.id,
                    user_id=race_user.id,
                    status=AudioStatus.PENDING.value,
                )
                db.session.add(audio)
                db.session.flush()
                audio_story_ids.append(audio.id)
            db.session.commit()

        results = []
        with ThreadPoolExecutor(max_workers=thread_count) as executor:
            futures = {
                executor.submit(
                    _debit_in_thread,
                    app,
                    race_user.id,
                    1,
                    audio_story_ids[i],
                    race_story.id,
                    i,
                ): i
                for i in range(thread_count)
            }
            for future in as_completed(futures):
                results.append(future.result())

        successes = [r for r in results if r[1]]
        assert len(successes) == 3, (
            f"Expected 3 successful debits (3 credits), got {len(successes)}"
        )

        with app.app_context():
            user = db.session.get(User, race_user.id)
            assert user.credits_balance == 0, (
                f"Expected balance=0, got {user.credits_balance}"
            )

            # Verify lot consistency
            total_remaining = (
                db.session.query(
                    db.func.coalesce(db.func.sum(CreditLot.amount_remaining), 0)
                )
                .filter(CreditLot.user_id == race_user.id)
                .scalar()
            )
            assert total_remaining == user.credits_balance, (
                f"Lot sum ({total_remaining}) != cached balance ({user.credits_balance})"
            )
