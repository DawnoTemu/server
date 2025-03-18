import requests
from config import Config
from io import BytesIO
import logging
import os
import sys

# Ensure the root directory is in the Python path
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

# Now import the audio_splitter module
from utils.audio_splitter import split_audio_file

# Configure logger
logger = logging.getLogger('voice_model')

class VoiceModel:
    """Model for voice cloning operations"""
    
    @staticmethod
    def create_api_session():
        """Create a session for ElevenLabs API with authentication"""
        session = requests.Session()
        session.headers.update({"xi-api-key": Config.ELEVENLABS_API_KEY})
        return session
    
    @staticmethod
    def clone_voice(file_data, filename, remove_background_noise=False):
        """
        Clone a voice using ElevenLabs API with support for large files
        
        Args:
            file_data: File-like object containing audio data
            filename: Original filename
            remove_background_noise: Whether to remove background noise (default: False)
            
        Returns:
            tuple: (success, data/error message)
        """
        try:
            session = VoiceModel.create_api_session()
            
            # Split audio into chunks if needed
            audio_chunks = split_audio_file(file_data, filename)
            logger.info(f"Split audio into {len(audio_chunks)} chunks")
            
            # Prepare multipart form data
            files = []
            
            # Add each audio chunk as a file with the same field name
            for chunk_filename, chunk_file, mime_type in audio_chunks:
                files.append(("files", (chunk_filename, chunk_file, mime_type)))
            
            # Add other form fields
            files.append(("name", (None, Config.VOICE_NAME)))
            files.append(("description", (None, "Cloned voice from user upload")))
            files.append(("remove_background_noise", (None, str(remove_background_noise).lower())))
            
            # Make API request
            response = session.post(
                "https://api.elevenlabs.io/v1/voices/add",
                files=files
            )
            
            if response.status_code == 200:
                return True, response.json()
            else:
                error_detail = "Cloning failed"
                try:
                    error_detail = response.json().get("detail", error_detail)
                except:
                    pass
                logger.error(f"ElevenLabs API error: {response.status_code} - {error_detail}")
                return False, error_detail
                
        except Exception as e:
            logger.error(f"Exception in clone_voice: {str(e)}")
            return False, str(e)
    
    @staticmethod
    def delete_voice(voice_id):
        """
        Delete a voice from ElevenLabs
        
        Args:
            voice_id: ID of the voice to delete
            
        Returns:
            tuple: (success, message)
        """
        try:
            session = VoiceModel.create_api_session()
            
            # Make API request
            response = session.delete(
                f"https://api.elevenlabs.io/v1/voices/{voice_id}"
            )
            
            if response.status_code == 200:
                return True, "Voice deleted successfully"
            else:
                return False, response.json().get("detail", "Deletion failed")
                
        except Exception as e:
            return False, str(e)