import pytest
import json
from unittest.mock import patch, MagicMock
from io import BytesIO


class TestVoiceRoutes:
    """Tests for the voice routes"""
    
    @patch('controllers.voice_controller.VoiceController.clone_voice')
    def test_clone_voice_success(self, mock_clone, client):
        """Test successfully cloning a voice"""
        # Arrange
        mock_clone.return_value = (
            True, 
            {"voice_id": "test-voice-id", "name": "Test Voice"}, 
            200
        )
        
        # Create a test file
        test_file = (BytesIO(b'test audio data'), 'test.wav')
        
        # Act
        response = client.post(
            '/api/clone',
            data={'file': test_file},
            content_type='multipart/form-data'
        )
        
        # Assert
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["voice_id"] == "test-voice-id"
        assert data["name"] == "Test Voice"
        
        # The file object passed to the controller will be different,
        # so we can't directly check the call args

    def test_clone_voice_no_file(self, client):
        """Test cloning a voice without providing a file"""
        # Act
        response = client.post(
            '/api/clone',
            data={},  # No file
            content_type='multipart/form-data'
        )
        
        # Assert
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "error" in data
        assert "No file provided" in data["error"]

    @patch('controllers.voice_controller.VoiceController.clone_voice')
    def test_clone_voice_error(self, mock_clone, client):
        """Test error handling when cloning a voice"""
        # Arrange
        mock_clone.return_value = (
            False, 
            {"error": "Invalid audio format"}, 
            400
        )
        
        # Create a test file
        test_file = (BytesIO(b'test audio data'), 'test.wav')
        
        # Act
        response = client.post(
            '/api/clone',
            data={'file': test_file},
            content_type='multipart/form-data'
        )
        
        # Assert
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "error" in data
        assert "Invalid audio format" in data["error"]

    @patch('controllers.voice_controller.VoiceController.delete_voice')
    def test_delete_voice_success(self, mock_delete, client):
        """Test successfully deleting a voice"""
        # Arrange
        voice_id = "test-voice-id"
        mock_delete.return_value = (
            True, 
            {"message": "Voice and associated files deleted"}, 
            200
        )
        
        # Act
        response = client.delete(f'/api/voices/{voice_id}')
        
        # Assert
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "message" in data
        assert "Voice and associated files deleted" in data["message"]
        mock_delete.assert_called_once_with(voice_id)

    @patch('controllers.voice_controller.VoiceController.delete_voice')
    def test_delete_voice_error(self, mock_delete, client):
        """Test error handling when deleting a voice"""
        # Arrange
        voice_id = "test-voice-id"
        mock_delete.return_value = (
            False, 
            {"error": "Voice not found", "details": "Not found in ElevenLabs"}, 
            404
        )
        
        # Act
        response = client.delete(f'/api/voices/{voice_id}')
        
        # Assert
        assert response.status_code == 404
        data = json.loads(response.data)
        assert "error" in data
        assert "Voice not found" in data["error"]
        assert "details" in data
        assert "Not found in ElevenLabs" in data["details"]
        mock_delete.assert_called_once_with(voice_id)