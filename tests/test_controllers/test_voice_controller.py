import pytest
from unittest.mock import patch, MagicMock
from types import SimpleNamespace

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
        success, message, status_code = VoiceController.clone_voice(file, user_id=1)
        
        # Assert
        assert success is False
        assert message == {"error": "No file provided"}
        assert status_code == 400

    def test_clone_voice_empty_filename(self):
        """Test handling when filename is empty"""
        # Arrange
        mock_file = MagicMock()
        mock_file.filename = ""
        
        # Act
        success, message, status_code = VoiceController.clone_voice(mock_file, user_id=1)
        
        # Assert
        assert success is False
        assert message == {"error": "No file provided"}
        assert status_code == 400

    @patch('controllers.voice_controller.VoiceController.allowed_file')
    def test_clone_voice_invalid_file_type(self, mock_allowed):
        """Test handling invalid file types"""
        # Arrange
        mock_file = MagicMock()
        mock_file.filename = "sample.txt"
        mock_allowed.return_value = False
        
        # Act
        success, message, status_code = VoiceController.clone_voice(mock_file, user_id=1)
        
        # Assert
        assert success is False
        assert message == {"error": "Invalid file type"}
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
        mock_clone.return_value = (
            True,
            {"id": 123, "name": "Test Voice", "status": "recorded", "task_id": "task-1"},
        )
        
        # Act
        success, result, status_code = VoiceController.clone_voice(mock_file, user_id=1)
        
        # Assert
        assert success is True
        assert result["status"] == "recorded"
        assert status_code == 201
        mock_allowed.assert_called_once_with(mock_file.filename)
        mock_clone.assert_called_once_with(mock_file.stream, mock_file.filename, 1, voice_name=None)

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
        success, result, status_code = VoiceController.clone_voice(mock_file, user_id=1)
        
        # Assert
        assert success is False
        assert result == {"error": "API error message"}
        assert status_code == 500
        mock_clone.assert_called_once_with(mock_file.stream, mock_file.filename, 1, voice_name=None)

    @patch('models.audio_model.AudioModel.delete_voice_audio')
    @patch('models.voice_model.VoiceModel.delete_voice')
    def test_delete_voice_success(self, mock_delete, mock_delete_audio):
        """Test successful voice deletion cleans up audio first"""
        voice_id = 42
        mock_delete_audio.return_value = (True, "Audio deleted")
        mock_delete.return_value = (True, "Voice deleted successfully")

        success, result, status_code = VoiceController.delete_voice(voice_id)

        assert success is True
        assert "deleted" in result["message"].lower()
        assert status_code == 200
        mock_delete_audio.assert_called_once_with(voice_id)
        mock_delete.assert_called_once_with(voice_id)

    @patch('models.audio_model.AudioModel.delete_voice_audio')
    @patch('models.voice_model.VoiceModel.delete_voice')
    def test_delete_voice_api_error(self, mock_delete, mock_delete_audio):
        """Test handling API errors during voice deletion"""
        voice_id = 42
        mock_delete_audio.return_value = (True, "Audio deleted")
        mock_delete.return_value = (False, "API error")

        success, result, status_code = VoiceController.delete_voice(voice_id)

        assert success is False
        assert "Failed to delete voice" in result["error"]
        assert "API error" in result["details"]
        assert status_code == 500

    @patch('models.audio_model.AudioModel.delete_voice_audio')
    @patch('models.voice_model.VoiceModel.delete_voice')
    def test_delete_voice_audio_error(self, mock_delete_voice, mock_delete_audio):
        """Test handling audio deletion errors during voice deletion"""
        voice_id = 42
        mock_delete_voice.return_value = (True, "Voice deleted successfully")
        mock_delete_audio.return_value = (False, "S3 error")

        success, result, status_code = VoiceController.delete_voice(voice_id)

        assert success is True
        assert "Voice deleted, but failed" in result["message"]
        assert "S3 error" in result["details"]
        assert status_code == 200
        mock_delete_audio.assert_called_once_with(voice_id)

    @patch('models.audio_model.AudioModel.delete_voice_audio')
    @patch('models.voice_model.VoiceModel.delete_voice')
    def test_delete_voice_audio_cleanup_before_voice_delete(self, mock_delete, mock_delete_audio):
        """Audio records must be deleted BEFORE the voice record to avoid FK orphans."""
        voice_id = 42
        call_order = []

        def track_audio(*args, **kwargs):
            call_order.append("delete_audio")
            return True, "ok"

        def track_voice(*args, **kwargs):
            call_order.append("delete_voice")
            return True, "ok"

        mock_delete_audio.side_effect = track_audio
        mock_delete.side_effect = track_voice

        VoiceController.delete_voice(voice_id)

        assert call_order == ["delete_audio", "delete_voice"]
