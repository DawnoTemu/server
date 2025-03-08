import requests
from config import Config
from io import BytesIO

class VoiceModel:
    """Model for voice cloning operations"""
    
    @staticmethod
    def create_api_session():
        """Create a session for ElevenLabs API with authentication"""
        session = requests.Session()
        session.headers.update({"xi-api-key": Config.ELEVENLABS_API_KEY})
        return session
    
    @staticmethod
    def clone_voice(file_data, filename):
        """
        Clone a voice using ElevenLabs API
        
        Args:
            file_data: File-like object containing audio data
            filename: Original filename
            
        Returns:
            tuple: (success, data/error message)
        """
        try:
            session = VoiceModel.create_api_session()
            
            # Prepare multipart form data
            files = {
                "files": (filename, file_data, 
                          "audio/wav" if filename.lower().endswith('.wav') else "audio/mpeg"),
                "name": (None, Config.VOICE_NAME),
                "description": (None, "Cloned voice from user upload"),
            }
            
            # Make API request
            response = session.post(
                "https://api.elevenlabs.io/v1/voices/add",
                files=files
            )
            
            if response.status_code == 200:
                return True, response.json()
            else:
                return False, response.json().get("detail", "Cloning failed")
                
        except Exception as e:
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