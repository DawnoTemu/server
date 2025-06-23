import pytest
import os
from io import BytesIO
from unittest.mock import patch
from utils.voice_service import VoiceService
from config import Config

class TestVoiceService:
    """Test cases for the unified VoiceService"""
    
    def test_get_active_service_default(self):
        """Test getting the active service with default config"""
        with patch('config.Config.PREFERRED_VOICE_SERVICE', 'elevenlabs'):
            service = VoiceService.get_active_service()
            assert service == VoiceService.ELEVENLABS
    
    def test_get_active_service_cartesia(self):
        """Test getting the active service when set to cartesia"""
        with patch('config.Config.PREFERRED_VOICE_SERVICE', 'cartesia'):
            service = VoiceService.get_active_service()
            assert service == VoiceService.CARTESIA
            
    def test_get_active_service_unknown(self):
        """Test getting the active service with unknown value"""
        with patch('config.Config.PREFERRED_VOICE_SERVICE', 'unknown_service'):
            service = VoiceService.get_active_service()
            assert service == VoiceService.ELEVENLABS  # Should default to ElevenLabs
    
    def test_is_service_available_elevenlabs(self):
        """Test checking if ElevenLabs is available"""
        with patch('config.Config.ELEVENLABS_API_KEY', 'test_key'):
            assert VoiceService.is_service_available(VoiceService.ELEVENLABS) is True
            
        with patch('config.Config.ELEVENLABS_API_KEY', None):
            assert VoiceService.is_service_available(VoiceService.ELEVENLABS) is False
    
    def test_is_service_available_cartesia(self):
        """Test checking if Cartesia is available"""
        with patch('config.Config.CARTESIA_API_KEY', 'test_key'):
            assert VoiceService.is_service_available(VoiceService.CARTESIA) is True
            
        with patch('config.Config.CARTESIA_API_KEY', None):
            assert VoiceService.is_service_available(VoiceService.CARTESIA) is False
    
    def test_clone_voice_elevenlabs(self, mock_elevenlabs_session, sample_audio_file):
        """Test cloning voice with ElevenLabs"""
        with patch('config.Config.PREFERRED_VOICE_SERVICE', 'elevenlabs'):
            with patch('config.Config.ELEVENLABS_API_KEY', 'test_key'):
                success, data = VoiceService.clone_voice(
                    file_data=sample_audio_file,
                    filename="test_voice.mp3",
                    user_id=123,
                    voice_name="Test Voice"
                )
                
                assert success is True
                assert "voice_id" in data
    
    def test_clone_voice_cartesia(self, mock_cartesia_session, sample_audio_file):
        """Test cloning voice with Cartesia"""
        with patch('config.Config.PREFERRED_VOICE_SERVICE', 'cartesia'):
            with patch('config.Config.CARTESIA_API_KEY', 'test_key'):
                success, data = VoiceService.clone_voice(
                    file_data=sample_audio_file,
                    filename="test_voice.mp3",
                    user_id=123,
                    voice_name="Test Voice",
                    language="en"
                )
                
                assert success is True
                assert "voice_id" in data
    
    def test_delete_voice_elevenlabs(self, mock_elevenlabs_session):
        """Test deleting voice with ElevenLabs"""
        with patch('config.Config.PREFERRED_VOICE_SERVICE', 'elevenlabs'):
            with patch('config.Config.ELEVENLABS_API_KEY', 'test_key'):
                success, message = VoiceService.delete_voice(
                    voice_id=123,
                    external_voice_id="test-voice-id-123"
                )
                
                assert success is True
    
    def test_delete_voice_cartesia(self, mock_cartesia_session):
        """Test deleting voice with Cartesia"""
        with patch('config.Config.PREFERRED_VOICE_SERVICE', 'cartesia'):
            with patch('config.Config.CARTESIA_API_KEY', 'test_key'):
                success, message = VoiceService.delete_voice(
                    voice_id=123,
                    external_voice_id="test-voice-id-789"
                )
                
                assert success is True
    
    def test_synthesize_speech_elevenlabs(self, mock_elevenlabs_session):
        """Test synthesizing speech with ElevenLabs"""
        with patch('config.Config.PREFERRED_VOICE_SERVICE', 'elevenlabs'):
            with patch('config.Config.ELEVENLABS_API_KEY', 'test_key'):
                success, audio_data = VoiceService.synthesize_speech(
                    external_voice_id="test-voice-id-123",
                    text="This is a test of the ElevenLabs speech synthesis"
                )
                
                assert success is True
                assert isinstance(audio_data, BytesIO)
    
    def test_synthesize_speech_cartesia(self, mock_cartesia_session):
        """Test synthesizing speech with Cartesia"""
        with patch('config.Config.PREFERRED_VOICE_SERVICE', 'cartesia'):
            with patch('config.Config.CARTESIA_API_KEY', 'test_key'):
                success, audio_data = VoiceService.synthesize_speech(
                    external_voice_id="test-voice-id-789",
                    text="This is a test of the Cartesia speech synthesis",
                    language="en"
                )
                
                assert success is True
                assert isinstance(audio_data, BytesIO)
    
    def test_fallback_when_service_not_available(self, mock_elevenlabs_session, mock_cartesia_session, sample_audio_file):
        """Test falling back to another service when the preferred one is not available"""
        with patch('config.Config.PREFERRED_VOICE_SERVICE', 'elevenlabs'):
            with patch('config.Config.ELEVENLABS_API_KEY', None):
                with patch('config.Config.CARTESIA_API_KEY', 'test_key'):
                    success, data = VoiceService.clone_voice(
                        file_data=sample_audio_file,
                        filename="test_voice.mp3",
                        user_id=123,
                        voice_name="Test Voice"
                    )
                    
                    assert success is True  # Should fall back to Cartesia 