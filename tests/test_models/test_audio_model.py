import pytest
from unittest.mock import patch, MagicMock
from io import BytesIO
from botocore.exceptions import ClientError

from models.audio_model import AudioModel, AudioStory, AudioStatus
from models.story_model import Story
from models.voice_model import Voice, VoiceStatus, VoiceAllocationStatus, VoiceServiceProvider
from models.user_model import User
from database import db


class TestAudioModel:
    """Tests for the AudioModel class"""

    def test_synthesize_speech_success(self, mock_elevenlabs_session):
        """Test successful speech synthesis"""
        voice_id = "test-voice-id"
        text = "This is a test story content."

        success, result = AudioModel.synthesize_speech(voice_id, text)

        assert success is True
        assert isinstance(result, BytesIO)

    def test_synthesize_speech_api_error(self, mock_elevenlabs_session):
        """Test speech synthesis with API error"""
        voice_id = "test-voice-id"
        text = "This is a test story content."
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("API Error")
        mock_elevenlabs_session.post.return_value = mock_response

        success, result = AudioModel.synthesize_speech(voice_id, text)

        assert success is False
        assert "API Error" in str(result)

    def test_store_audio_success(self, app):
        """Test successful audio storage in S3"""
        with app.app_context():
            user = User(email="audio-test@example.com", is_active=True, email_confirmed=True)
            user.set_password("Password123!")
            db.session.add(user)
            db.session.commit()

            story = Story(title="Test", author="Author", description="Desc", content="Content")
            db.session.add(story)
            db.session.commit()

            voice = Voice(
                name="Test Voice", user_id=user.id,
                status=VoiceStatus.READY, allocation_status=VoiceAllocationStatus.READY,
                service_provider=VoiceServiceProvider.ELEVENLABS,
            )
            db.session.add(voice)
            db.session.commit()

            audio_record = AudioStory(
                story_id=story.id, voice_id=voice.id, user_id=user.id,
                status=AudioStatus.PENDING.value,
            )
            db.session.add(audio_record)
            db.session.commit()

            audio_data = BytesIO(b'test audio data')
            with patch('utils.s3_client.S3Client.upload_fileobj', return_value=True):
                success, message = AudioModel.store_audio(audio_data, voice.id, story.id, audio_record)

            assert success is True
            assert "successfully" in message

    def test_store_audio_s3_error(self, app):
        """Test audio storage with S3 error"""
        with app.app_context():
            user = User(email="audio-err@example.com", is_active=True, email_confirmed=True)
            user.set_password("Password123!")
            db.session.add(user)
            db.session.commit()

            story = Story(title="Test", author="Author", description="Desc", content="Content")
            db.session.add(story)
            db.session.commit()

            voice = Voice(
                name="Test Voice", user_id=user.id,
                status=VoiceStatus.READY, allocation_status=VoiceAllocationStatus.READY,
                service_provider=VoiceServiceProvider.ELEVENLABS,
            )
            db.session.add(voice)
            db.session.commit()

            audio_record = AudioStory(
                story_id=story.id, voice_id=voice.id, user_id=user.id,
                status=AudioStatus.PENDING.value,
            )
            db.session.add(audio_record)
            db.session.commit()

            audio_data = BytesIO(b'test audio data')
            with patch('utils.s3_client.S3Client.upload_fileobj', side_effect=Exception("S3 Error")):
                success, message = AudioModel.store_audio(audio_data, voice.id, story.id, audio_record)

            assert success is False
            assert "S3 Error" in message

    def test_check_audio_exists_true(self, app):
        """Test checking if audio exists when it does"""
        with app.app_context():
            user = User(email="check-audio@example.com", is_active=True, email_confirmed=True)
            user.set_password("Password123!")
            db.session.add(user)
            db.session.commit()

            story = Story(title="Test", author="Author", description="Desc", content="Content")
            db.session.add(story)
            db.session.commit()

            voice = Voice(
                name="Test Voice", user_id=user.id,
                status=VoiceStatus.READY, allocation_status=VoiceAllocationStatus.READY,
                service_provider=VoiceServiceProvider.ELEVENLABS,
            )
            db.session.add(voice)
            db.session.commit()

            audio_record = AudioStory(
                story_id=story.id, voice_id=voice.id, user_id=user.id,
                status=AudioStatus.READY.value,
                s3_key="audio_stories/test/1.mp3",
            )
            db.session.add(audio_record)
            db.session.commit()

            mock_s3 = MagicMock()
            mock_s3.head_object.return_value = {}
            with patch('utils.s3_client.S3Client.get_client', return_value=mock_s3):
                with patch('utils.s3_client.S3Client.get_bucket_name', return_value='test-bucket'):
                    exists = AudioModel.check_audio_exists(voice.id, story.id)

            assert exists is True

    def test_check_audio_exists_false(self, app):
        """Test checking if audio exists when it doesn't"""
        with app.app_context():
            exists = AudioModel.check_audio_exists(99999, 99999)
            assert exists is False

    def test_get_audio_not_found(self, app):
        """Test audio retrieval when record doesn't exist"""
        with app.app_context():
            success, data, extra = AudioModel.get_audio(99999, 99999)
            assert success is False
            assert extra is None

    def test_delete_voice_audio_no_records(self, app):
        """Test deletion when no audio records exist"""
        with app.app_context():
            success, message = AudioModel.delete_voice_audio(99999)
            assert success is True
            assert "No audio records" in message

    def test_delete_voice_audio_success(self, app):
        """Test successful deletion of voice audio records"""
        with app.app_context():
            user = User(email="del-audio@example.com", is_active=True, email_confirmed=True)
            user.set_password("Password123!")
            db.session.add(user)
            db.session.commit()

            story = Story(title="Test", author="Author", description="Desc", content="Content")
            db.session.add(story)
            db.session.commit()

            voice = Voice(
                name="Test Voice", user_id=user.id,
                status=VoiceStatus.READY, allocation_status=VoiceAllocationStatus.READY,
                service_provider=VoiceServiceProvider.ELEVENLABS,
            )
            db.session.add(voice)
            db.session.commit()

            audio_record = AudioStory(
                story_id=story.id, voice_id=voice.id, user_id=user.id,
                status=AudioStatus.READY.value,
                s3_key="audio_stories/test/1.mp3",
            )
            db.session.add(audio_record)
            db.session.commit()

            with patch('utils.s3_client.S3Client.delete_objects', return_value=(True, 1, [])):
                success, message = AudioModel.delete_voice_audio(voice.id)

            assert success is True
            assert AudioStory.query.filter_by(voice_id=voice.id).count() == 0
