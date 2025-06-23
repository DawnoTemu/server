import pytest
import os
from io import BytesIO
from utils.cartesia_service import CartesiaService

class TestCartesiaService:
    """Test cases for the CartesiaService"""
    
    def test_create_session(self, mock_cartesia_session):
        """Test creating a session with authentication"""
        session = CartesiaService.create_session()
        assert session is not None
        assert mock_cartesia_session is session
        
        # Verify headers
        assert "X-API-Key" in session.headers
        assert "Cartesia-Version" in session.headers
        assert session.headers["Cartesia-Version"] == CartesiaService.API_VERSION
        
    def test_clone_voice(self, mock_cartesia_session, sample_audio_file):
        """Test voice cloning API call"""
        files = [("voice_sample.mp3", sample_audio_file, "audio/mpeg")]
        success, data = CartesiaService.clone_voice(
            files=files, 
            voice_name="Test Voice", 
            voice_description="Test voice description",
            mode="stability"
        )
        
        assert success is True
        assert "voice_id" in data
        assert data["voice_id"] == "test-voice-id-789"
        assert data["name"] == "Test Voice"
        
        # Verify the correct API endpoint was called
        mock_cartesia_session.post.assert_called_once()
        args, kwargs = mock_cartesia_session.post.call_args
        assert args[0] == f"{CartesiaService.API_BASE_URL}/voices/clone"
        
        # Verify payload
        assert "data" in kwargs
        assert kwargs["data"]["name"] == "Test Voice"
        assert kwargs["data"]["mode"] == "stability"
        assert kwargs["data"]["language"] == "pl"  # Default
        
        # Verify file was sent correctly
        assert "files" in kwargs
        assert "clip" in kwargs["files"]
        
    def test_create_voice(self, mock_cartesia_session):
        """Test voice creation API call"""
        # Sample embedding (192-dim vector)
        embedding = [0.1] * 192
        
        success, data = CartesiaService.create_voice(
            name="Test Direct Voice",
            description="Created via API",
            embedding=embedding,
            language="en"
        )
        
        assert success is True
        assert "voice_id" in data
        
        # Verify correct API endpoint was called
        mock_cartesia_session.post.assert_called()
        args, kwargs = mock_cartesia_session.post.call_args_list[-1]
        assert args[0] == f"{CartesiaService.API_BASE_URL}/voices/"
        
        # Verify JSON payload
        assert "json" in kwargs
        json_payload = kwargs["json"]
        assert json_payload["name"] == "Test Direct Voice"
        assert json_payload["description"] == "Created via API"
        assert json_payload["language"] == "en"
        assert json_payload["embedding"] == embedding
        assert len(json_payload["embedding"]) == 192
        
    def test_delete_voice(self, mock_cartesia_session):
        """Test voice deletion API call"""
        success, message = CartesiaService.delete_voice("test-voice-id-789")
        
        assert success is True
        assert "deleted from Cartesia" in message
        
        # Verify the correct API endpoint was called
        mock_cartesia_session.delete.assert_called_once()
        args, kwargs = mock_cartesia_session.delete.call_args
        assert args[0] == f"{CartesiaService.API_BASE_URL}/voices/test-voice-id-789"
        
    def test_synthesize_speech(self, mock_cartesia_session):
        """Test speech synthesis API call"""
        success, audio_data = CartesiaService.synthesize_speech(
            "test-voice-id-789", 
            "This is a test of the Cartesia speech synthesis API"
        )
        
        assert success is True
        assert isinstance(audio_data, BytesIO)
        
        # Verify the correct API endpoint was called
        mock_cartesia_session.post.assert_called()
        args, kwargs = mock_cartesia_session.post.call_args_list[-1]
        assert args[0] == f"{CartesiaService.API_BASE_URL}/tts/bytes"
        
        # Verify request payload
        json_payload = kwargs.get("json", {})
        assert json_payload["transcript"] == "This is a test of the Cartesia speech synthesis API"
        assert json_payload["voice"]["id"] == "test-voice-id-789"
        assert json_payload["model_id"] == CartesiaService.MODELS["SONIC_2"]  # Default model
        assert json_payload["language"] == "pl"  # Default language
        
    def test_synthesize_speech_with_model(self, mock_cartesia_session):
        """Test speech synthesis API call with specific model"""
        success, audio_data = CartesiaService.synthesize_speech(
            "test-voice-id-789", 
            "This is a test with Sonic Turbo model",
            model_id=CartesiaService.MODELS["SONIC_TURBO"],
            speed="fast"
        )
        
        assert success is True
        
        # Verify request payload has the correct model
        args, kwargs = mock_cartesia_session.post.call_args_list[-1]
        json_payload = kwargs.get("json", {})
        assert json_payload["model_id"] == CartesiaService.MODELS["SONIC_TURBO"]
        assert json_payload["speed"] == "fast"

    def test_synthesize_speech_with_custom_language(self, mock_cartesia_session):
        """Test speech synthesis API call with custom language"""
        success, audio_data = CartesiaService.synthesize_speech(
            "test-voice-id-789", 
            "This is a test with English language",
            language="en"
        )
        
        assert success is True
        
        # Verify request payload has the correct language
        args, kwargs = mock_cartesia_session.post.call_args_list[-1]
        json_payload = kwargs.get("json", {})
        assert json_payload["language"] == "en" 