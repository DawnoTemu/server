import pytest
from unittest.mock import patch, MagicMock
from io import BytesIO
from botocore.exceptions import ClientError

from models.audio_model import AudioModel


class TestAudioModel:
    """Tests for the AudioModel class"""

    def test_synthesize_speech_success(self, mock_elevenlabs_session):
        """Test successful speech synthesis"""
        # Arrange
        voice_id = "test-voice-id"
        text = "This is a test story content."
        
        # Act
        success, result = AudioModel.synthesize_speech(voice_id, text)
        
        # Assert
        assert success is True
        assert isinstance(result, BytesIO)
        mock_elevenlabs_session.post.assert_called_once()
        assert f"text-to-speech/{voice_id}/stream" in mock_elevenlabs_session.post.call_args[0][0]

    def test_synthesize_speech_api_error(self, mock_elevenlabs_session):
        """Test speech synthesis with API error"""
        # Arrange
        voice_id = "test-voice-id"
        text = "This is a test story content."
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("API Error")
        mock_elevenlabs_session.post.return_value = mock_response
        
        # Act
        success, result = AudioModel.synthesize_speech(voice_id, text)
        
        # Assert
        assert success is False
        assert "API Error" in str(result)

    def test_store_audio_success(self, mock_s3_client):
        """Test successful audio storage in S3"""
        # Arrange
        audio_data = BytesIO(b'test audio data')
        voice_id = "test-voice-id"
        story_id = 1
        
        # Act
        success, message = AudioModel.store_audio(audio_data, voice_id, story_id)
        
        # Assert
        assert success is True
        assert "successfully" in message
        mock_s3_client.upload_fileobj.assert_called_once()

    def test_store_audio_s3_error(self, mock_s3_client):
        """Test audio storage with S3 error"""
        # Arrange
        audio_data = BytesIO(b'test audio data')
        voice_id = "test-voice-id"
        story_id = 1
        mock_s3_client.upload_fileobj.side_effect = Exception("S3 Error")
        
        # Act
        success, message = AudioModel.store_audio(audio_data, voice_id, story_id)
        
        # Assert
        assert success is False
        assert "S3 Error" in message

    def test_check_audio_exists_true(self, mock_s3_client):
        """Test checking if audio exists when it does"""
        # Arrange
        voice_id = "test-voice-id"
        story_id = 1
        
        # Act
        exists = AudioModel.check_audio_exists(voice_id, story_id)
        
        # Assert
        assert exists is True
        mock_s3_client.head_object.assert_called_once()

    def test_check_audio_exists_false(self, mock_s3_client):
        """Test checking if audio exists when it doesn't"""
        # Arrange
        voice_id = "test-voice-id"
        story_id = 1
        mock_s3_client.head_object.side_effect = ClientError(
            {'Error': {'Code': 'NoSuchKey'}}, 'head_object')
        
        # Act
        exists = AudioModel.check_audio_exists(voice_id, story_id)
        
        # Assert
        assert exists is False

    def test_get_audio_success(self, mock_s3_client):
        """Test successful audio retrieval from S3"""
        # Arrange
        voice_id = "test-voice-id"
        story_id = 1
        
        # Act
        success, data, extra = AudioModel.get_audio(voice_id, story_id)
        
        # Assert
        assert success is True
        assert data == b'mock audio data'
        assert extra['content_length'] == 1000
        mock_s3_client.get_object.assert_called_once()

    def test_get_audio_with_range(self, mock_s3_client):
        """Test audio retrieval with range header"""
        # Arrange
        voice_id = "test-voice-id"
        story_id = 1
        range_header = "bytes=0-100"
        
        # Act
        success, data, extra = AudioModel.get_audio(voice_id, story_id, range_header)
        
        # Assert
        assert success is True
        assert 'Range' in mock_s3_client.get_object.call_args[1]
        assert mock_s3_client.get_object.call_args[1]['Range'] == range_header

    def test_get_audio_error(self, mock_s3_client):
        """Test audio retrieval with S3 error"""
        # Arrange
        voice_id = "test-voice-id"
        story_id = 1
        mock_s3_client.get_object.side_effect = ClientError(
            {'Error': {'Code': 'NoSuchKey'}}, 'get_object')
        
        # Act
        success, data, extra = AudioModel.get_audio(voice_id, story_id)
        
        # Assert
        assert success is False
        assert "NoSuchKey" in str(data)
        assert extra is None

    def test_delete_voice_audio_success(self, mock_s3_client):
        """Test successful deletion of voice audio files"""
        # Arrange
        voice_id = "test-voice-id"
        
        # Act
        success, message = AudioModel.delete_voice_audio(voice_id)
        
        # Assert
        assert success is True
        assert "2 audio files" in message  # Because our mock has 2 objects
        mock_s3_client.delete_objects.assert_called_once()

    def test_delete_voice_audio_no_files(self, mock_s3_client):
        """Test deletion when no audio files exist"""
        # Arrange
        voice_id = "test-voice-id"
        mock_page = {}  # No Contents key
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [mock_page]
        mock_s3_client.get_paginator.return_value = mock_paginator
        
        # Act
        success, message = AudioModel.delete_voice_audio(voice_id)
        
        # Assert
        assert success is True
        assert "0 audio files" in message
        mock_s3_client.delete_objects.assert_not_called()

    def test_delete_voice_audio_error(self, mock_s3_client):
        """Test deletion with S3 error"""
        # Arrange
        voice_id = "test-voice-id"
        mock_s3_client.delete_objects.side_effect = Exception("S3 Error")
        
        # Act
        success, message = AudioModel.delete_voice_audio(voice_id)
        
        # Assert
        assert success is False
        assert "S3 Error" in message