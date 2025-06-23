import logging
from io import BytesIO
from cartesia import Cartesia
from cartesia.core.api_error import ApiError
from config import Config

# Configure logger
logger = logging.getLogger('cartesia_sdk_service')

class CartesiaSDKService:
    """
    Service for handling all Cartesia API operations using the official SDK
    """
    
    @staticmethod
    def get_client():
        """
        Get an authenticated Cartesia client
        
        Returns:
            Cartesia: Authenticated client
        """
        try:
            return Cartesia(
                api_key=Config.CARTESIA_API_KEY,
                timeout=60.0  # Set a reasonable timeout
            )
        except Exception as e:
            logger.error(f"Failed to create Cartesia client: {str(e)}")
            raise
    
    @staticmethod
    def clone_voice(files, voice_name, voice_description=None, language="pl", mode="similarity", enhance=False):
        """
        Make API call to Cartesia for voice cloning using the SDK
        
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
            # Get the client
            client = CartesiaSDKService.get_client()
            
            # Extract the first file (Cartesia SDK expects a single file)
            if files and len(files) > 0:
                _, file_data, _ = files[0]
                
                # Clone the voice
                cloned_voice = client.voices.clone(
                    clip=file_data,  # File object from the first file
                    name=voice_name,
                    description=voice_description or f"Voice for {voice_name}",
                    language=language,
                    mode=mode,  # "similarity" or "stability"
                    enhance=enhance
                )
                
                # Return success with voice data
                return True, {
                    "voice_id": cloned_voice.id,
                    "name": cloned_voice.name,
                    "data": cloned_voice
                }
            else:
                return False, "No audio files provided"
            
        except ApiError as e:
            # Handle specific API errors from Cartesia
            logger.error(f"Cartesia API error: {e.status_code} - {e.body}")
            
            # Handle payment required error explicitly
            if e.status_code == 402:
                return False, f"Payment required: Please check your Cartesia account billing status and API limits"
                
            return False, f"API error: {e.body}"
            
        except Exception as e:
            logger.error(f"Exception in clone_voice: {str(e)}")
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
            client = CartesiaSDKService.get_client()
            
            # Delete the voice
            client.voices.delete(id=cartesia_voice_id)
            
            return True, "Voice deleted from Cartesia"
            
        except ApiError as e:
            logger.error(f"Cartesia API error: {e.status_code} - {e.body}")
            return False, f"API error: {e.body}"
            
        except Exception as e:
            logger.error(f"Exception in delete_voice: {str(e)}")
            return False, str(e)
    
    @staticmethod
    def synthesize_speech(cartesia_voice_id, text, model_id="sonic-2", language="pl", speed="slow"):
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
            client = CartesiaSDKService.get_client()
            
            # Prepare voice controls if speed is specified
            voice_controls = {}
            if speed in ["slow", "normal", "fast"]:
                voice_controls = {"speed": speed}
            
            logger.info(f"Attempting speech synthesis with voice {cartesia_voice_id}")
            
            # Prepare voice object with mode: "id" as per API documentation
            voice = {
                "mode": "id",
                "id": cartesia_voice_id
            }
            
            # Add experimental controls if specified
            if voice_controls:
                voice["experimental_controls"] = voice_controls
            
            # Prepare correct output_format as per API documentation
            # https://docs.cartesia.ai/2024-11-13/api-reference/tts/bytes
            output_format = {
                "container": "mp3",
                "bit_rate": 128000,
                "sample_rate": 44100
            }
            
            # Prepare parameters
            params = {
                "model_id": model_id,
                "transcript": text,
                "voice": voice,
                "output_format": output_format,
                "language": language
            }
            
            logger.info(f"Sending TTS request with params: {params}")
            
            # Generate audio - this returns a generator
            response_generator = client.tts.bytes(**params)
            
            # Consume the generator to get the bytes
            audio_chunks = []
            for chunk in response_generator:
                audio_chunks.append(chunk)
            
            audio_bytes = b''.join(audio_chunks)
            
            # If we got data, return it
            if audio_bytes:
                logger.info(f"Speech synthesis successful with {len(audio_bytes)} bytes")
                return True, BytesIO(audio_bytes)
            else:
                logger.error("Received empty audio response")
                return False, "Received empty audio response"
                
        except ApiError as e:
            logger.error(f"Cartesia API error: {e.status_code} - {e.body}")
            
            # Handle payment required error explicitly
            if e.status_code == 402:
                return False, f"Payment required: Please check your Cartesia account billing status and API limits"
                
            return False, f"API error: {e.body}"
            
        except Exception as e:
            logger.error(f"Exception in synthesize_speech: {str(e)}")
            return False, str(e)
    
    @staticmethod
    def list_voices():
        """
        List all available voices
        
        Returns:
            tuple: (success, voices/error message)
        """
        try:
            client = CartesiaSDKService.get_client()
            
            # Get all voices
            voices = list(client.voices.list())
            
            return True, voices
            
        except ApiError as e:
            logger.error(f"Cartesia API error: {e.status_code} - {e.body}")
            return False, f"API error: {e.body}"
            
        except Exception as e:
            logger.error(f"Exception in list_voices: {str(e)}")
            return False, str(e) 