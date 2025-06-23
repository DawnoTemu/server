import requests
from io import BytesIO
import logging
from config import Config

# Configure logger
logger = logging.getLogger('cartesia_service')

class CartesiaService:
    """
    Service for handling all Cartesia API operations
    """
    
    # Cartesia API base URL
    API_BASE_URL = "https://api.cartesia.ai"
    API_VERSION = "2024-11-13"
    
    # Available models
    MODELS = {
        "SONIC_2": "sonic-2",
        "SONIC_TURBO": "sonic-turbo"
    }
    
    @staticmethod
    def create_session():
        """
        Create a new authenticated session for Cartesia API
        
        Returns:
            requests.Session: Authenticated session object
        """
        session = requests.Session()
        session.headers.update({
            "X-API-Key": Config.CARTESIA_API_KEY,
            "Cartesia-Version": CartesiaService.API_VERSION
        })
        return session
    
    @staticmethod
    def clone_voice(files, voice_name, voice_description=None, language="pl", mode="similarity", enhance=True):
        """
        Make API call to Cartesia for voice cloning
        
        Args:
            files: List of audio file tuples in the format [(filename, file_data, mime_type), ...]
            voice_name: Name for the voice
            voice_description: Description for the voice
            language: Language code (default: "pl" for Polish)
            mode: Cloning mode - "stability" or "similarity"
            enhance: Whether to reduce background noise
            
        Returns:
            tuple: (success, data/error message)
        """
        try:
            session = CartesiaService.create_session()
            
            # Prepare multipart form data
            form_files = {}
            
            # Only use the first audio file
            if files and len(files) > 0:
                filename, file_data, _ = files[0]
                form_files["clip"] = (filename, file_data)
            else:
                return False, "No audio files provided"
            
            # Add other form fields
            payload = {
                "name": voice_name,
                "language": language,
                "mode": mode,
                "enhance": str(enhance).lower()
            }
            
            if voice_description:
                payload["description"] = voice_description
            
            # Make API request
            response = session.post(
                f"{CartesiaService.API_BASE_URL}/voices/clone",
                data=payload,
                files=form_files
            )
            
            if response.status_code == 200:
                # Get the Cartesia voice ID from response
                cartesia_data = response.json()
                cartesia_voice_id = cartesia_data.get("id")
                
                if not cartesia_voice_id:
                    logger.error("Cartesia API did not return a voice_id")
                    return False, "Voice cloning failed: No voice ID returned"
                
                # Return successful response with voice data
                return True, {
                    "voice_id": cartesia_voice_id,
                    "name": voice_name,
                    "data": cartesia_data
                }
            else:
                error_detail = "Cloning failed"
                try:
                    error_detail = response.json().get("error", error_detail)
                except:
                    pass
                logger.error(f"Cartesia API error: {response.status_code} - {error_detail}")
                return False, error_detail
                
        except Exception as e:
            logger.error(f"Exception in clone_voice: {str(e)}")
            return False, str(e)
    
    @staticmethod
    def create_voice(name, description, embedding, language="pl", base_voice_id=None):
        """
        Create a voice directly using voice features
        
        Args:
            name: Name for the voice
            description: Description for the voice
            embedding: 192-dimensional vector that represents the voice
            language: Language code (default: "pl" for Polish)
            base_voice_id: Optional base voice ID
            
        Returns:
            tuple: (success, data/error message)
        """
        try:
            session = CartesiaService.create_session()
            
            # Prepare request payload
            payload = {
                "name": name,
                "description": description,
                "embedding": embedding,
                "language": language
            }
            
            if base_voice_id:
                payload["base_voice_id"] = base_voice_id
            
            # Make API request
            response = session.post(
                f"{CartesiaService.API_BASE_URL}/voices/",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                voice_data = response.json()
                voice_id = voice_data.get("id")
                
                if not voice_id:
                    logger.error("Cartesia API did not return a voice_id")
                    return False, "Voice creation failed: No voice ID returned"
                
                return True, {
                    "voice_id": voice_id,
                    "name": name,
                    "data": voice_data
                }
            else:
                error_detail = "Voice creation failed"
                try:
                    error_detail = response.json().get("error", error_detail)
                except:
                    pass
                logger.error(f"Cartesia API error: {response.status_code} - {error_detail}")
                return False, error_detail
        
        except Exception as e:
            logger.error(f"Exception in create_voice: {str(e)}")
            return False, str(e)
    
    @staticmethod
    def delete_voice(cartesia_voice_id):
        """
        Delete a voice from Cartesia
        
        Args:
            cartesia_voice_id: Cartesia voice ID
            
        Returns:
            tuple: (success, message)
        """
        try:
            session = CartesiaService.create_session()
            
            # Make API request
            response = session.delete(
                f"{CartesiaService.API_BASE_URL}/voices/{cartesia_voice_id}"
            )
            
            if response.status_code == 200:
                return True, "Voice deleted from Cartesia"
            else:
                error_detail = "Deletion failed"
                try:
                    error_detail = response.json().get("error", error_detail)
                except:
                    pass
                logger.error(f"Cartesia API error: {response.status_code} - {error_detail}")
                return False, error_detail
                
        except Exception as e:
            logger.error(f"Exception in delete_voice: {str(e)}")
            return False, str(e)
    
    @staticmethod
    def synthesize_speech(cartesia_voice_id, text, model_id=None, language="pl", speed="normal"):
        """
        Synthesize speech using Cartesia API
        
        Args:
            cartesia_voice_id: Cartesia voice ID
            text: Text to synthesize
            model_id: Model ID to use (default: sonic-2)
            language: Language code (default: "pl" for Polish)
            speed: Speed of speech ("slow", "normal", "fast")
            
        Returns:
            tuple: (success, audio_data/error message)
        """
        try:
            session = CartesiaService.create_session()
            
            # Use sonic-2 by default
            if not model_id:
                model_id = CartesiaService.MODELS["SONIC_2"]
            
            # Prepare voice object
            voice = {
                "id": cartesia_voice_id
            }
            
            # Prepare output format object
            output_format = {
                "type": "mp3"
            }
            
            # Prepare request payload
            payload = {
                "model_id": model_id,
                "transcript": text,
                "voice": voice,
                "output_format": output_format,
                "language": language
            }
            
            # Add speed if provided
            if speed in ["slow", "normal", "fast"]:
                payload["speed"] = speed
            
            # Make API request
            response = session.post(
                f"{CartesiaService.API_BASE_URL}/tts/bytes",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            response.raise_for_status()
            return True, BytesIO(response.content)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error synthesizing speech: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    return False, e.response.json().get('error', str(e))
                except:
                    return False, str(e)
            return False, str(e)
        except Exception as e:
            logger.error(f"Unexpected error in synthesize_speech: {str(e)}")
            return False, str(e) 