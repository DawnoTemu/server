import pytest
import json
from unittest.mock import patch, MagicMock
from types import SimpleNamespace
from io import BytesIO


class TestVoiceRoutes:
    """Tests for the voice routes"""
    
    @patch('utils.auth_middleware.UserModel.get_by_id', return_value=SimpleNamespace(id=1, is_active=True, email_confirmed=True))
    @patch('utils.auth_middleware.jwt.decode', return_value={'type': 'access', 'sub': 1})
    @patch('controllers.voice_controller.VoiceController.clone_voice')
    def test_clone_voice_success(self, mock_clone, mock_jwt_decode, mock_get_user, client):
        """Test successfully cloning a voice"""
        # Arrange
        mock_clone.return_value = (
            True, 
            {"id": 321, "name": "Test Voice", "status": "recorded", "task_id": "task-xyz"}, 
            201
        )
        
        # Create a test file
        test_file = (BytesIO(b'test audio data'), 'test.wav')
        
        # Act
        response = client.post(
            '/voices',
            data={'file': test_file},
            content_type='multipart/form-data',
            headers={'Authorization': 'Bearer test-token'}
        )
        
        # Assert
        assert response.status_code == 201
        data = json.loads(response.data)
        assert data["status"] == "recorded"
        assert data["name"] == "Test Voice"
        
        # The file object passed to the controller will be different,
        # so we can't directly check the call args

    @patch('utils.auth_middleware.UserModel.get_by_id', return_value=SimpleNamespace(id=1, is_active=True, email_confirmed=True))
    @patch('utils.auth_middleware.jwt.decode', return_value={'type': 'access', 'sub': 1})
    def test_clone_voice_no_file(self, mock_jwt_decode, mock_get_user, client):
        """Test cloning a voice without providing a file"""
        # Act
        response = client.post(
            '/voices',
            data={},  # No file
            content_type='multipart/form-data',
            headers={'Authorization': 'Bearer test-token'}
        )
        
        # Assert
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "error" in data
        assert "No file provided" in data["error"]

    @patch('utils.auth_middleware.UserModel.get_by_id', return_value=SimpleNamespace(id=1, is_active=True, email_confirmed=True))
    @patch('utils.auth_middleware.jwt.decode', return_value={'type': 'access', 'sub': 1})
    @patch('controllers.voice_controller.VoiceController.clone_voice')
    def test_clone_voice_error(self, mock_clone, mock_jwt_decode, mock_get_user, client):
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
            '/voices',
            data={'file': test_file},
            content_type='multipart/form-data',
            headers={'Authorization': 'Bearer test-token'}
        )
        
        # Assert
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "error" in data
        assert "Invalid audio format" in data["error"]

    @patch('controllers.voice_controller.VoiceController.get_voice', return_value=(True, {'user_id': 1}, 200))
    @patch('utils.auth_middleware.UserModel.get_by_id', return_value=SimpleNamespace(id=1, is_active=True, email_confirmed=True))
    @patch('utils.auth_middleware.jwt.decode', return_value={'type': 'access', 'sub': 1})
    @patch('controllers.voice_controller.VoiceController.delete_voice')
    def test_delete_voice_success(self, mock_delete, mock_jwt_decode, mock_get_user, mock_get_voice, client):
        """Test successfully deleting a voice"""
        # Arrange
        voice_id = 123
        mock_delete.return_value = (
            True, 
            {"message": "Voice and associated files deleted"}, 
            200
        )
        
        # Act
        response = client.delete(f'/voices/{voice_id}', headers={'Authorization': 'Bearer test-token'})
        
        # Assert
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "message" in data
        assert "Voice and associated files deleted" in data["message"]
        mock_delete.assert_called_once_with(voice_id)

    @patch('controllers.voice_controller.VoiceController.get_voice', return_value=(True, {'user_id': 1}, 200))
    @patch('utils.auth_middleware.UserModel.get_by_id', return_value=SimpleNamespace(id=1, is_active=True, email_confirmed=True))
    @patch('utils.auth_middleware.jwt.decode', return_value={'type': 'access', 'sub': 1})
    @patch('controllers.voice_controller.VoiceController.delete_voice')
    def test_delete_voice_error(self, mock_delete, mock_jwt_decode, mock_get_user, mock_get_voice, client):
        """Test error handling when deleting a voice"""
        # Arrange
        voice_id = 123
        mock_delete.return_value = (
            False, 
            {"error": "Voice not found", "details": "Not found in ElevenLabs"}, 
            404
        )
        
        # Act
        response = client.delete(f'/voices/{voice_id}', headers={'Authorization': 'Bearer test-token'})
        
        # Assert
        assert response.status_code == 404
        data = json.loads(response.data)
        assert "error" in data
        assert "Voice not found" in data["error"]
        assert "details" in data
        assert "Not found in ElevenLabs" in data["details"]
        mock_delete.assert_called_once_with(voice_id)
