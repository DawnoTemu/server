import requests
from io import BytesIO
import logging
from config import Config

# Configure logger
logger = logging.getLogger('elevenlabs_service')

class ElevenLabsService:
    """
    Service for handling all ElevenLabs API operations
    """
    
    # ElevenLabs API base URL
    API_BASE_URL = "https://api.elevenlabs.io/v1"
    
    @staticmethod
    def create_session():
        """
        Create a new authenticated session for ElevenLabs API
        
        Returns:
            requests.Session: Authenticated session object
        """
        session = requests.Session()
        session.headers.update({"xi-api-key": Config.ELEVENLABS_API_KEY})
        return session
    
    @staticmethod
    def clone_voice(files, voice_name, voice_description, remove_background_noise=False):
        """
        Make API call to ElevenLabs for voice cloning
        
        Args:
            files: List of audio file tuples in the format [(filename, file_data, mime_type), ...]
            voice_name: Name for the voice
            voice_description: Description for the voice
            remove_background_noise: Whether to remove background noise
            
        Returns:
            tuple: (success, data/error message)
        """
        try:
            session = ElevenLabsService.create_session()
            
            # Prepare multipart form data
            form_files = []
            
            # Add each audio chunk as a file with the same field name
            for filename, file_data, mime_type in files:
                form_files.append(("files", (filename, file_data, mime_type)))
            
            # Add other form fields
            form_files.append(("name", (None, voice_name)))
            form_files.append(("description", (None, voice_description)))
            form_files.append(("remove_background_noise", (None, str(remove_background_noise).lower())))
            
            # Make API request
            response = session.post(
                f"{ElevenLabsService.API_BASE_URL}/voices/add",
                files=form_files
            )
            
            if response.status_code == 200:
                # Get the ElevenLabs voice ID from response
                elevenlabs_data = response.json()
                elevenlabs_voice_id = elevenlabs_data.get("voice_id")
                
                if not elevenlabs_voice_id:
                    logger.error("ElevenLabs API did not return a voice_id")
                    return False, "Voice cloning failed: No voice ID returned"
                
                # Return successful response with voice data
                return True, {
                    "voice_id": elevenlabs_voice_id,
                    "name": voice_name
                }
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
    def delete_voice(elevenlabs_voice_id):
        """
        Delete a voice from ElevenLabs
        
        Args:
            elevenlabs_voice_id: ElevenLabs voice ID
            
        Returns:
            tuple: (success, message)
        """
        try:
            session = ElevenLabsService.create_session()
            
            # Make API request
            response = session.delete(
                f"{ElevenLabsService.API_BASE_URL}/voices/{elevenlabs_voice_id}"
            )
            
            if response.status_code == 200:
                return True, "Voice deleted from ElevenLabs"
            else:
                error_detail = "Deletion failed"
                try:
                    error_detail = response.json().get("detail", error_detail)
                except:
                    pass
                logger.error(f"ElevenLabs API error: {response.status_code} - {error_detail}")
                return False, error_detail
                
        except Exception as e:
            logger.error(f"Exception in delete_voice: {str(e)}")
            return False, str(e)
    
    @staticmethod
    def synthesize_speech(elevenlabs_voice_id, text):
        """
        Synthesize speech using ElevenLabs API
        
        Args:
            elevenlabs_voice_id: ElevenLabs voice ID
            text: Text to synthesize
            
        Returns:
            tuple: (success, audio_data/error message)
        """
        try:
            session = ElevenLabsService.create_session()
            
            # Use a session with keep-alive for better performance
            response = session.post(
                f"{ElevenLabsService.API_BASE_URL}/text-to-speech/{elevenlabs_voice_id}/stream",
                json={
                    "text": text,
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {
                        "stability": 0.65,
                        "similarity_boost": 0.9,
                        "style": 0.1,
                        "use_speaker_boost": True,
                        "speed": 1.0
                    }
                },
                headers={"Accept": "audio/mpeg"}
            )

            if response.status_code == 429:
                # Surface structured rate-limit info so callers can back off
                retry_after = response.headers.get("Retry-After")
                try:
                    body = response.json()
                except Exception:
                    body = {}
                message = body.get("message") or body.get("detail") or response.text
                return False, {
                    "error": "rate_limited",
                    "status_code": 429,
                    "message": message,
                    "retry_after": retry_after,
                }

            response.raise_for_status()
            return True, BytesIO(response.content)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error synthesizing speech: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    return False, e.response.json().get('detail', str(e))
                except:
                    return False, str(e)
            return False, str(e)
        except Exception as e:
            logger.error(f"Unexpected error in synthesize_speech: {str(e)}")
            return False, str(e) 
