import pytest
import json
from unittest.mock import patch, MagicMock
from io import BytesIO


class TestAudioRoutes:
    """Tests for the audio routes"""
    
    @patch('controllers.audio_controller.AudioController.get_audio')
    def test_get_audio_success(self, mock_get_audio, client):
        """Test successfully getting audio data"""
        # Arrange
        voice_id = "test-voice-id"
        story_id = 1
        mock_audio_data = b'test audio data'
        mock_get_audio.return_value = (True, mock_audio_data, 200, {'content_length': 14})
        
        # Act
        response = client.get(f'/api/audio/{voice_id}/{story_id}.mp3')
        
        # Assert
        assert response.status_code == 200
        assert response.data == mock_audio_data
        assert response.headers.get('Content-Type') == 'audio/mpeg'
        assert response.headers.get('Accept-Ranges') == 'bytes'
        assert response.headers.get('Content-Length') == '14'
        mock_get_audio.assert_called_once_with(voice_id, story_id, None)

    @patch('controllers.audio_controller.AudioController.get_audio')
    def test_get_audio_with_range(self, mock_get_audio, client):
        """Test getting audio data with range header"""
        # Arrange
        voice_id = "test-voice-id"
        story_id = 1
        range_header = "bytes=0-100"
        mock_audio_data = b'partial audio data'
        mock_get_audio.return_value = (
            True, 
            mock_audio_data, 
            206, 
            {'content_length': 101, 'content_range': 'bytes 0-100/500'}
        )
        
        # Act
        response = client.get(
            f'/api/audio/{voice_id}/{story_id}.mp3',
            headers={'Range': range_header}
        )
        
        # Assert
        assert response.status_code == 206
        assert response.data == mock_audio_data
        assert response.headers.get('Content-Range') == 'bytes 0-100/500'
        mock_get_audio.assert_called_once_with(voice_id, story_id, range_header)

    @patch('controllers.audio_controller.AudioController.get_audio')
    def test_get_audio_not_found(self, mock_get_audio, client):
        """Test getting audio that doesn't exist"""
        # Arrange
        voice_id = "test-voice-id"
        story_id = 999
        mock_get_audio.return_value = (False, {"error": "Audio not found"}, 404, None)
        
        # Act
        response = client.get(f'/api/audio/{voice_id}/{story_id}.mp3')
        
        # Assert
        assert response.status_code == 404
        data = json.loads(response.data)
        assert "error" in data
        assert data["error"] == "Audio not found"

    @patch('controllers.audio_controller.AudioController.check_audio_exists')
    def test_check_audio_exists_true(self, mock_check, client):
        """Test checking if audio exists when it does"""
        # Arrange
        voice_id = "test-voice-id"
        story_id = 1
        mock_check.return_value = (True, {"exists": True}, 200)
        
        # Act
        response = client.get(f'/api/audio/exists/{voice_id}/{story_id}')
        
        # Assert
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["exists"] is True
        mock_check.assert_called_once_with(voice_id, story_id)

    @patch('controllers.audio_controller.AudioController.check_audio_exists')
    def test_check_audio_exists_false(self, mock_check, client):
        """Test checking if audio exists when it doesn't"""
        # Arrange
        voice_id = "test-voice-id"
        story_id = 999
        mock_check.return_value = (True, {"exists": False}, 200)
        
        # Act
        response = client.get(f'/api/audio/exists/{voice_id}/{story_id}')
        
        # Assert
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["exists"] is False

    @patch('controllers.audio_controller.AudioController.check_audio_exists')
    def test_check_audio_exists_error(self, mock_check, client):
        """Test error handling when checking if audio exists"""
        # Arrange
        voice_id = "test-voice-id"
        story_id = 1
        mock_check.return_value = (False, {"error": "S3 connection error"}, 500)
        
        # Act
        response = client.get(f'/api/audio/exists/{voice_id}/{story_id}')
        
        # Assert
        assert response.status_code == 500
        data = json.loads(response.data)
        assert "error" in data
        assert "S3 connection error" in data["error"]

    @patch('controllers.audio_controller.AudioController.synthesize_audio')
    def test_synthesize_speech_success(self, mock_synthesize, client):
        """Test successfully synthesizing speech"""
        # Arrange
        mock_synthesize.return_value = (
            True, 
            {"status": "success", "url": "https://example.com/audio.mp3"}, 
            200
        )
        request_data = {
            "voice_id": "test-voice-id",
            "story_id": 1
        }
        
        # Act
        response = client.post(
            '/api/synthesize',
            json=request_data,
            content_type='application/json'
        )
        
        # Assert
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "success"
        assert data["url"] == "https://example.com/audio.mp3"
        mock_synthesize.assert_called_once_with("test-voice-id", 1)

    def test_synthesize_speech_missing_voice_id(self, client):
        """Test synthesizing speech with missing voice_id"""
        # Arrange
        request_data = {
            "story_id": 1
            # missing voice_id
        }
        
        # Act
        response = client.post(
            '/api/synthesize',
            json=request_data,
            content_type='application/json'
        )
        
        # Assert
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "error" in data
        assert "Missing voice_id" in data["error"]

    def test_synthesize_speech_missing_story_id(self, client):
        """Test synthesizing speech with missing story_id"""
        # Arrange
        request_data = {
            "voice_id": "test-voice-id"
            # missing story_id
        }
        
        # Act
        response = client.post(
            '/api/synthesize',
            json=request_data,
            content_type='application/json'
        )
        
        # Assert
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "error" in data
        assert "Missing story_id" in data["error"]

    @patch('controllers.audio_controller.AudioController.synthesize_audio')
    def test_synthesize_speech_synthesis_error(self, mock_synthesize, client):
        """Test error handling during speech synthesis"""
        # Arrange
        mock_synthesize.return_value = (
            False, 
            {"error": "Synthesis failed"}, 
            500
        )
        request_data = {
            "voice_id": "test-voice-id",
            "story_id": 1
        }
        
        # Act
        response = client.post(
            '/api/synthesize',
            json=request_data,
            content_type='application/json'
        )
        
        # Assert
        assert response.status_code == 500
        data = json.loads(response.data)
        assert "error" in data
        assert "Synthesis failed" in data["error"]