import pytest
from unittest.mock import patch, MagicMock

from controllers.voice_controller import VoiceController


class TestVoiceController:
    """Tests for the VoiceController class"""
    
    def test_allowed_file_valid(self):
        """Test checking that a file with valid extension is allowed"""
        # Act & Assert
        assert VoiceController.allowed_file("sample.wav") is True
        assert VoiceController.allowed_file("sample.mp3") is True

    def test_allowed_file_invalid(self):
        """Test checking that a file with invalid extension is not allowed"""
        # Act & Assert
        assert VoiceController.allowed_file("sample.txt") is False
        assert VoiceController.allowed_file("sample") is False
        assert VoiceController.allowed_file("mp3") is False

    def test_clone_voice_no_file(self):
        """Test handling when no file is provided"""
        # Arrange
        file = None
        
        # Act
        success, message, status_code = VoiceController.clone_voice(file)
        
        # Assert
        assert success is False
        assert message == "No file provided"
        assert status_code == 400

    def test_clone_voice_empty_filename(self):
        """Test handling when filename is empty"""
        # Arrange
        mock_file = MagicMock()
        mock_file.filename = ""
        
        # Act
        success, message, status_code = VoiceController.clone_voice(mock_file)
        
        # Assert
        assert success is False
        assert message == "No file provided"
        assert status_code == 400

    @patch('controllers.voice_controller.VoiceController.allowed_file')
    def test_clone_voice_invalid_file_type(self, mock_allowed):
        """Test handling invalid file types"""
        # Arrange
        mock_file = MagicMock()
        mock_file.filename = "sample.txt"
        mock_allowed.return_value = False
        
        # Act
        success, message, status_code = VoiceController.clone_voice(mock_file)
        
        # Assert
        assert success is False
        assert message == "Invalid file type"
        assert status_code == 400
        mock_allowed.assert_called_once_with(mock_file.filename)

    @patch('controllers.voice_controller.VoiceController.allowed_file')
    @patch('models.voice_model.VoiceModel.clone_voice')
    def test_clone_voice_success(self, mock_clone, mock_allowed):
        """Test successful voice cloning"""
        # Arrange
        mock_file = MagicMock()
        mock_file.filename = "sample.wav"
        mock_allowed.return_value = True
        mock_clone.return_value = (True, {"voice_id": "test-voice-id", "name": "Test Voice"})
        
        # Act
        success, result, status_code = VoiceController.clone_voice(mock_file)
        
        # Assert
        assert success is True
        assert result["voice_id"] == "test-voice-id"
        assert status_code == 200
        mock_allowed.assert_called_once_with(mock_file.filename)
        mock_clone.assert_called_once_with(mock_file.stream, mock_file.filename)

    @patch('controllers.voice_controller.VoiceController.allowed_file')
    @patch('models.voice_model.VoiceModel.clone_voice')
    def test_clone_voice_api_error(self, mock_clone, mock_allowed):
        """Test handling API errors during voice cloning"""
        # Arrange
        mock_file = MagicMock()
        mock_file.filename = "sample.wav"
        mock_allowed.return_value = True
        mock_clone.return_value = (False, "API error message")
        
        # Act
        success, result, status_code = VoiceController.clone_voice(mock_file)
        
        # Assert
        assert success is False
        assert result == "API error message"
        assert status_code == 500

    @patch('models.voice_model.VoiceModel.delete_voice')
    def test_delete_voice_success(self, mock_delete):
        """Test successful voice deletion"""
        # Arrange
        voice_id = "test-voice-id"
        mock_delete.return_value = (True, "Voice deleted successfully")
        
        # Act
        success, result, status_code = VoiceController.delete_voice(voice_id)
        
        # Assert
        assert success is True
        assert "message" in result
        assert "Voice deleted" in result["message"]
        assert status_code == 200
        mock_delete.assert_called_once_with(voice_id)

    @patch('models.voice_model.VoiceModel.delete_voice')
    def test_delete_voice_api_error(self, mock_delete):
        """Test handling API errors during voice deletion"""
        # Arrange
        voice_id = "test-voice-id"
        mock_delete.return_value = (False, "API error")
        
        # Act
        success, result, status_code = VoiceController.delete_voice(voice_id)
        
        # Assert
        assert success is False
        assert "error" in result
        assert "Failed to delete voice" in result["error"]
        assert "API error" in result["details"]
        assert status_code == 500

    @patch('models.voice_model.VoiceModel.delete_voice')
    @patch('models.audio_model.AudioModel.delete_voice_audio')
    def test_delete_voice_audio_error(self, mock_delete_audio, mock_delete_voice):
        """Test handling audio deletion errors during voice deletion"""
        # Arrange
        voice_id = "test-voice-id"
        mock_delete_voice.return_value = (True, "Voice deleted successfully")
        mock_delete_audio.return_value = (False, "S3 error")
        
        # Act
        success, result, status_code = VoiceController.delete_voice(voice_id)
        
        # Assert
        assert success is True
        assert "message" in result
        assert "Voice deleted, but failed" in result["message"]
        assert "S3 error" in result["details"]
        assert status_code == 200