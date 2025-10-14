from datetime import datetime

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
        assert success is True
        warnings = details.get("warnings", [])
        assert warnings
        assert any(
            warning.get("type") == "voice_service"
            and warning.get("details", {}).get("voice_id") == voice.id
            and "Rate limited" in str(warning.get("details", {}).get("message"))
            for warning in warnings
        )
