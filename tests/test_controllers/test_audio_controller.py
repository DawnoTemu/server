import pytest
from unittest.mock import patch, MagicMock
from io import BytesIO

from controllers.audio_controller import AudioController


class TestAudioController:
    """Tests for the AudioController class"""

    @patch('models.audio_model.AudioModel.check_audio_exists')
    def test_check_audio_exists_success(self, mock_check):
        """Test successfully checking if audio exists"""
        # Arrange
        voice_id = "test-voice-id"
        story_id = 1
        mock_check.return_value = True
        
        # Act
        success, data, status_code = AudioController.check_audio_exists(voice_id, story_id)
        
        # Assert
        assert success is True
        assert data["exists"] is True
        assert status_code == 200
        mock_check.assert_called_once_with(voice_id, story_id)

    @patch('models.audio_model.AudioModel.check_audio_exists')
    def test_check_audio_exists_error(self, mock_check):
        """Test error handling when checking if audio exists"""
        # Arrange
        voice_id = "test-voice-id"
        story_id = 1
        mock_check.side_effect = Exception("S3 connection error")
        
        # Act
        success, data, status_code = AudioController.check_audio_exists(voice_id, story_id)
        
        # Assert
        assert success is False
        assert "error" in data
        assert "S3 connection error" in data["error"]
        assert status_code == 500

    @patch('models.audio_model.AudioModel.get_audio')
    def test_get_audio_success(self, mock_get_audio):
        """Test successfully getting audio data"""
        # Arrange
        voice_id = "test-voice-id"
        story_id = 1
        range_header = "bytes=0-100"
        mock_get_audio.return_value = (True, b'test audio data', {'content_length': 101, 'content_range': range_header})
        
        # Act
        success, data, status_code, extra = AudioController.get_audio(voice_id, story_id, range_header)
        
        # Assert
        assert success is True
        assert data == b'test audio data'
        assert status_code == (206 if range_header else 200)
        assert extra['content_length'] == 101
        assert extra['content_range'] == range_header
        mock_get_audio.assert_called_once_with(voice_id, story_id, range_header)

    @patch('models.audio_model.AudioModel.get_audio')
    def test_get_audio_not_found(self, mock_get_audio):
        """Test getting audio that doesn't exist"""
        # Arrange
        voice_id = "test-voice-id"
        story_id = 1
        mock_get_audio.return_value = (False, "Audio not found", None)
        
        # Act
        success, data, status_code, extra = AudioController.get_audio(voice_id, story_id)
        
        # Assert
        assert success is False
        assert "error" in data
        assert "Audio not found" in data["error"]
        assert status_code == 404
        assert extra is None

    @patch('models.story_model.StoryModel.get_story_by_id')
    @patch('models.audio_model.AudioModel.synthesize_speech')
    @patch('models.audio_model.AudioModel.store_audio')
    @patch('config.Config.get_s3_client')
    def test_synthesize_audio_success(self, mock_s3_client, mock_store, mock_synthesize, mock_get_story):
        """Test successfully synthesizing audio"""
        # Arrange
        voice_id = "test-voice-id"
        story_id = 1
        
        # Configure mocks
        mock_get_story.return_value = {"content": "Test story content"}
        mock_synthesize.return_value = (True, BytesIO(b'synthesized audio'))
        mock_store.return_value = (True, "Audio stored successfully")
        mock_s3_client.return_value.generate_presigned_url.return_value = "https://test-url.com/audio.mp3"
        
        # Act
        success, data, status_code = AudioController.synthesize_audio(voice_id, story_id)
        
        # Assert
        assert success is True
        assert data["status"] == "success"
        assert "url" in data
        assert status_code == 200
        mock_get_story.assert_called_once_with(story_id)
        mock_synthesize.assert_called_once()
        mock_store.assert_called_once()

    @patch('models.story_model.StoryModel.get_story_by_id')
    def test_synthesize_audio_story_not_found(self, mock_get_story):
        """Test synthesizing audio for a non-existent story"""
        # Arrange
        voice_id = "test-voice-id"
        story_id = 999
        mock_get_story.return_value = None
        
        # Act
        success, data, status_code = AudioController.synthesize_audio(voice_id, story_id)
        
        # Assert
        assert success is False
        assert "error" in data
        assert "Story not found" in data["error"]
        assert status_code == 404

    @patch('models.story_model.StoryModel.get_story_by_id')
    def test_synthesize_audio_no_content(self, mock_get_story):
        """Test synthesizing audio with missing story content"""
        # Arrange
        voice_id = "test-voice-id"
        story_id = 1
        mock_get_story.return_value = {"title": "Story without content"}  # No content key
        
        # Act
        success, data, status_code = AudioController.synthesize_audio(voice_id, story_id)
        
        # Assert
        assert success is False
        assert "error" in data
        assert "Story text not found" in data["error"]
        assert status_code == 400

    @patch('models.story_model.StoryModel.get_story_by_id')
    @patch('models.audio_model.AudioModel.synthesize_speech')
    def test_synthesize_audio_synthesis_failure(self, mock_synthesize, mock_get_story):
        """Test handling synthesis failure"""
        # Arrange
        voice_id = "test-voice-id"
        story_id = 1
        mock_get_story.return_value = {"content": "Test story content"}
        mock_synthesize.return_value = (False, "Synthesis API error")
        
        # Act
        success, data, status_code = AudioController.synthesize_audio(voice_id, story_id)
        
        # Assert
        assert success is False
        assert "error" in data
        assert "Synthesis failed" in data["error"]
        assert status_code == 500

    @patch('models.story_model.StoryModel.get_story_by_id')
    @patch('models.audio_model.AudioModel.synthesize_speech')
    @patch('models.audio_model.AudioModel.store_audio')
    def test_synthesize_audio_storage_failure(self, mock_store, mock_synthesize, mock_get_story):
        """Test handling storage failure"""
        # Arrange
        voice_id = "test-voice-id"
        story_id = 1
        mock_get_story.return_value = {"content": "Test story content"}
        mock_synthesize.return_value = (True, BytesIO(b'synthesized audio'))
        mock_store.return_value = (False, "S3 storage error")
        
        # Act
        success, data, status_code = AudioController.synthesize_audio(voice_id, story_id)
        
        # Assert
        assert success is False
        assert "error" in data
        assert "Storage failed" in data["error"]
        assert status_code == 500

    @patch('models.story_model.StoryModel.get_story_by_id')
    def test_synthesize_audio_unexpected_error(self, mock_get_story):
        """Test handling unexpected errors during synthesis"""
        # Arrange
        voice_id = "test-voice-id"
        story_id = 1
        mock_get_story.side_effect = Exception("Unexpected error")
        
        # Act
        success, data, status_code = AudioController.synthesize_audio(voice_id, story_id)
        
        # Assert
        assert success is False
        assert "error" in data
        assert "Unexpected error" in data["error"]
        assert status_code == 500