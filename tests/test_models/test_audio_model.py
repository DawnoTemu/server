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

    def test_get_audio_with_range(self, app):
        """Test Range header forwarding to S3 for audio streaming"""
        with app.app_context():
            user = User(email="range-audio@example.com", is_active=True, email_confirmed=True)
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

            mock_body = MagicMock()
            mock_body.read.return_value = b'partial audio data'
            mock_s3 = MagicMock()
            mock_s3.get_object.return_value = {
                'Body': mock_body,
                'ContentLength': 18,
                'ContentType': 'audio/mpeg',
                'ContentRange': 'bytes 0-17/1000',
            }

            with patch('utils.s3_client.S3Client.get_client', return_value=mock_s3), \
                 patch('utils.s3_client.S3Client.get_bucket_name', return_value='test-bucket'):
                success, content, extra = AudioModel.get_audio(
                    voice.id, story.id, range_header="bytes=0-17"
                )

            assert success is True
            assert content == b'partial audio data'
            assert extra['content_range'] == 'bytes 0-17/1000'
            mock_s3.get_object.assert_called_once_with(
                Bucket='test-bucket',
                Key='audio_stories/test/1.mp3',
                Range='bytes=0-17',
            )

    def test_get_audio_s3_error(self, app):
        """Test S3 ClientError handling during audio retrieval"""
        with app.app_context():
            user = User(email="s3err-audio@example.com", is_active=True, email_confirmed=True)
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
            mock_s3.get_object.side_effect = ClientError(
                {'Error': {'Code': 'NoSuchKey', 'Message': 'Not Found'}},
                'GetObject',
            )

            with patch('utils.s3_client.S3Client.get_client', return_value=mock_s3), \
                 patch('utils.s3_client.S3Client.get_bucket_name', return_value='test-bucket'):
                success, message, extra = AudioModel.get_audio(voice.id, story.id)

            assert success is False
            assert "not found" in message.lower()
            assert extra is None

    def test_delete_voice_audio_s3_error(self, app):
        """Test S3 error handling during voice audio deletion"""
        with app.app_context():
            user = User(email="del-s3err@example.com", is_active=True, email_confirmed=True)
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

            with patch('utils.s3_client.S3Client.delete_objects', return_value=(False, 0, ['error deleting'])):
                success, message = AudioModel.delete_voice_audio(voice.id)

            assert success is True
            assert "issues with S3" in message
            assert AudioStory.query.filter_by(voice_id=voice.id).count() == 0

    def test_delete_voice_audio_no_files(self, app):
        """Test deletion edge case when records exist but have no S3 keys"""
        with app.app_context():
            user = User(email="del-nofiles@example.com", is_active=True, email_confirmed=True)
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
                s3_key=None,
            )
            db.session.add(audio_record)
            db.session.commit()

            success, message = AudioModel.delete_voice_audio(voice.id)

            assert success is True
            assert "no s3 files" in message.lower()
            assert AudioStory.query.filter_by(voice_id=voice.id).count() == 0
