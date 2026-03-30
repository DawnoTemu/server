from datetime import datetime, timedelta

from database import db
from sqlalchemy import delete as sa_delete
from models.audio_model import AudioStory, AudioStatus
from models.story_model import Story
from models.user_model import UserModel, User
from models.voice_model import (
    Voice,
    VoiceAllocationStatus,
    VoiceServiceProvider,
    VoiceSlotEvent,
    VoiceSlotEventType,
    VoiceStatus,
)
from models.credit_model import CreditLot, CreditTransaction, CreditTransactionAllocation


def test_delete_user_removes_related_data(app, mocker):
    mocker.patch("utils.s3_client.S3Client.delete_objects", return_value=(True, 1, []))
    mocker.patch("models.voice_model.VoiceService.delete_voice", return_value=(True, "deleted"))

    with app.app_context():
        existing = UserModel.get_by_email("delete-me@example.com")
        if existing:
            existing_voice_ids = [
                voice.id for voice in Voice.query.filter_by(user_id=existing.id).all()
            ]
            if existing_voice_ids:
                db.session.execute(
                    sa_delete(VoiceSlotEvent).where(
                        VoiceSlotEvent.voice_id.in_(existing_voice_ids)
                    )
                )
                db.session.execute(
                    sa_delete(Voice).where(Voice.id.in_(existing_voice_ids))
                )
            db.session.delete(existing)
            db.session.commit()

        user = User(
            email="delete-me@example.com",
            is_active=True,
            email_confirmed=True,
            credits_balance=25,
        )
        user.set_password("CurrentPass1!")
        db.session.add(user)
        db.session.commit()

        story = Story(
            title="Sample Story",
            author="Author",
            description="Test",
            content="Once upon a time",
        )
        db.session.add(story)
        db.session.commit()

        voice = Voice(
            name="Account Voice",
            user_id=user.id,
            status=VoiceStatus.READY,
            allocation_status=VoiceAllocationStatus.READY,
            service_provider=VoiceServiceProvider.ELEVENLABS,
            created_at=datetime.utcnow(),
        )
        db.session.add(voice)
        db.session.commit()

        audio = AudioStory(
            story_id=story.id,
            voice_id=voice.id,
            user_id=user.id,
            status=AudioStatus.READY.value,
            s3_key="audio_stories/sample.mp3",
        )
        db.session.add(audio)
        db.session.commit()

        lot = CreditLot(
            user_id=user.id,
            source="free",
            amount_granted=10,
            amount_remaining=10,
        )
        tx = CreditTransaction(
            user_id=user.id,
            amount=10,
            type="credit",
            reason="initial",
            status="applied",
        )
        db.session.add_all([lot, tx])
        db.session.commit()

        allocation = CreditTransactionAllocation(
            transaction_id=tx.id,
            lot_id=lot.id,
            amount=10,
        )
        db.session.add(allocation)
        db.session.commit()

        event = VoiceSlotEvent(
            voice_id=voice.id,
            user_id=user.id,
            event_type=VoiceSlotEventType.ALLOCATION_COMPLETED,
            reason="test-cleanup",
        )
        db.session.add(event)
        db.session.commit()

        success, details = UserModel.delete_user(user.id)
        assert success is True
        assert isinstance(details, dict)
        assert details.get("warnings") == []

        assert UserModel.get_by_id(user.id) is None
        assert Voice.query.filter_by(user_id=user.id).count() == 0
        assert AudioStory.query.filter_by(user_id=user.id).count() == 0
        assert CreditTransaction.query.filter_by(user_id=user.id).count() == 0
        assert CreditLot.query.filter_by(user_id=user.id).count() == 0
        assert CreditTransactionAllocation.query.filter(CreditTransactionAllocation.lot_id == lot.id).count() == 0

        event_after = VoiceSlotEvent.query.get(event.id)
        assert event_after is not None
        assert event_after.user_id is None


def test_delete_user_surfaces_voice_service_failure(app, mocker):
    mocker.patch("utils.s3_client.S3Client.delete_objects", return_value=(True, 1, []))
    mocker.patch(
        "models.voice_model.VoiceService.delete_voice",
        return_value=(False, "Rate limited"),
    )

    with app.app_context():
        user = User(
            email="delete-me-fail@example.com",
            is_active=True,
            email_confirmed=True,
            credits_balance=0,
        )
        user.set_password("CurrentPass1!")
        db.session.add(user)
        db.session.commit()

        voice = Voice(
            name="Account Voice",
            user_id=user.id,
            status=VoiceStatus.READY,
            allocation_status=VoiceAllocationStatus.READY,
            service_provider=VoiceServiceProvider.ELEVENLABS,
            elevenlabs_voice_id="voice-123",
        )
        db.session.add(voice)
        db.session.commit()

        success, details = UserModel.delete_user(user.id)
        assert success is False
        assert "Rate limited" in str(details)


class TestTrialAndSubscriptionFields:
    def test_trial_is_active_when_future_expiry(self, app):
        with app.app_context():
            user = User(
                email="trial-future@example.com",
                is_active=True,
                email_confirmed=True,
                credits_balance=0,
                trial_expires_at=datetime.utcnow() + timedelta(days=7),
            )
            user.set_password("TestPass123!")
            db.session.add(user)
            db.session.commit()

            assert user.trial_is_active is True

    def test_trial_is_not_active_when_expired(self, app):
        with app.app_context():
            user = User(
                email="trial-expired@example.com",
                is_active=True,
                email_confirmed=True,
                credits_balance=0,
                trial_expires_at=datetime.utcnow() - timedelta(days=1),
            )
            user.set_password("TestPass123!")
            db.session.add(user)
            db.session.commit()

            assert user.trial_is_active is False

    def test_trial_is_not_active_when_null(self, app):
        with app.app_context():
            user = User(
                email="trial-null@example.com",
                is_active=True,
                email_confirmed=True,
                credits_balance=0,
                trial_expires_at=None,
            )
            user.set_password("TestPass123!")
            db.session.add(user)
            db.session.commit()

            assert user.trial_is_active is False

    def test_subscription_fields_default_values(self, app):
        with app.app_context():
            user = User(
                email="sub-defaults@example.com",
                is_active=True,
                email_confirmed=True,
                credits_balance=0,
            )
            user.set_password("TestPass123!")
            db.session.add(user)
            db.session.commit()

            assert user.subscription_active is False
            assert user.subscription_plan is None
            assert user.subscription_expires_at is None
            assert user.subscription_will_renew is False
            assert user.subscription_source is None
            assert user.revenuecat_app_user_id is None

    def test_revenuecat_app_user_id_lookup(self, app):
        with app.app_context():
            user = User(
                email="rc-lookup@example.com",
                is_active=True,
                email_confirmed=True,
                credits_balance=0,
                revenuecat_app_user_id="12345",
            )
            user.set_password("TestPass123!")
            db.session.add(user)
            db.session.commit()

            found = User.query.filter_by(revenuecat_app_user_id="12345").first()
            assert found is not None
            assert found.id == user.id

    def test_create_user_sets_trial_expires_at(self, app):
        with app.app_context():
            user = UserModel.create_user(
                email="trial-create@example.com",
                password="TestPass123!",
            )
            assert user.trial_expires_at is not None
            delta = user.trial_expires_at - datetime.utcnow()
            assert 13 <= delta.days <= 14

    def test_subscription_is_active_when_active_and_not_expired(self, app):
        with app.app_context():
            user = User(
                email="sub-active-check@example.com",
                is_active=True,
                email_confirmed=True,
                credits_balance=0,
                subscription_active=True,
                subscription_plan="monthly",
                subscription_expires_at=datetime.utcnow() + timedelta(days=30),
            )
            user.set_password("TestPass123!")
            db.session.add(user)
            db.session.commit()

            assert user.subscription_is_active is True

    def test_subscription_is_active_false_when_expired(self, app):
        with app.app_context():
            user = User(
                email="sub-expired-check@example.com",
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

            assert user.subscription_is_active is False

    def test_subscription_is_active_false_when_no_expiry(self, app):
        """Null expiration is treated as inactive to prevent accidental permanent access."""
        with app.app_context():
            user = User(
                email="sub-no-expiry@example.com",
                is_active=True,
                email_confirmed=True,
                credits_balance=0,
                subscription_active=True,
                subscription_plan="monthly",
                subscription_expires_at=None,
            )
            user.set_password("TestPass123!")
            db.session.add(user)
            db.session.commit()

            assert user.subscription_is_active is False

    def test_subscription_is_active_false_when_inactive(self, app):
        with app.app_context():
            user = User(
                email="sub-inactive-check@example.com",
                is_active=True,
                email_confirmed=True,
                credits_balance=0,
                subscription_active=False,
            )
            user.set_password("TestPass123!")
            db.session.add(user)
            db.session.commit()

            assert user.subscription_is_active is False

    def test_can_generate_with_trial(self, app):
        with app.app_context():
            user = User(
                email="can-gen-trial@example.com",
                is_active=True,
                email_confirmed=True,
                credits_balance=0,
                trial_expires_at=datetime.utcnow() + timedelta(days=7),
                subscription_active=False,
            )
            user.set_password("TestPass123!")
            db.session.add(user)
            db.session.commit()

            assert user.can_generate is True

    def test_can_generate_with_subscription(self, app):
        with app.app_context():
            user = User(
                email="can-gen-sub@example.com",
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

            assert user.can_generate is True

    def test_can_generate_false_when_nothing_active(self, app):
        with app.app_context():
            user = User(
                email="cant-gen@example.com",
                is_active=True,
                email_confirmed=True,
                credits_balance=0,
                trial_expires_at=datetime.utcnow() - timedelta(days=1),
                subscription_active=False,
            )
            user.set_password("TestPass123!")
            db.session.add(user)
            db.session.commit()

            assert user.can_generate is False

    def test_to_dict_includes_subscription_fields(self, app):
        with app.app_context():
            user = User(
                email="dict-test@example.com",
                is_active=True,
                email_confirmed=True,
                credits_balance=0,
                trial_expires_at=datetime.utcnow() + timedelta(days=7),
                subscription_active=True,
                subscription_plan="monthly",
                subscription_expires_at=datetime.utcnow() + timedelta(days=30),
            )
            user.set_password("TestPass123!")
            db.session.add(user)
            db.session.commit()

            d = user.to_dict()
            assert "trial_is_active" in d
            assert "trial_expires_at" in d
            assert "subscription_is_active" in d
            assert "subscription_plan" in d
            assert "can_generate" in d
            assert d["trial_is_active"] is True
            assert d["subscription_is_active"] is True
            assert d["subscription_plan"] == "monthly"
            assert d["can_generate"] is True
