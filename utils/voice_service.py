import logging
from io import BytesIO
from config import Config
from utils.elevenlabs_service import ElevenLabsService
from utils.cartesia_service import CartesiaService
from utils.cartesia_sdk_service import CartesiaSDKService

# Configure logger
logger = logging.getLogger('voice_service')

class VoiceService:
    """
    Unified service that routes voice operations to either ElevenLabs or Cartesia
    based on the configured preference in Config.PREFERRED_VOICE_SERVICE
    """
    
    # Service identifiers
    ELEVENLABS = "elevenlabs"
    CARTESIA = "cartesia"
    
    @staticmethod
    def get_active_service():
        """
        Get the active voice service based on configuration
        
        Returns:
            str: Service identifier
        """
        service = Config.PREFERRED_VOICE_SERVICE
        
        if service not in [VoiceService.ELEVENLABS, VoiceService.CARTESIA]:
            logger.warning(f"Unknown service: {service}, defaulting to {VoiceService.ELEVENLABS}")
            return VoiceService.ELEVENLABS
            
        return service
    
    @staticmethod
    def is_service_available(service=None):
        """
        Check if the specified service (or the active service) is available
        based on having the necessary API keys
        
        Args:
            service: Service to check (or active service if None)
            
        Returns:
            bool: True if service is available
        """
        if service is None:
            service = VoiceService.get_active_service()
            
        if service == VoiceService.ELEVENLABS:
            return bool(Config.ELEVENLABS_API_KEY)
        elif service == VoiceService.CARTESIA:
            return bool(Config.CARTESIA_API_KEY)
            
        return False
    
    @staticmethod
    def clone_voice(file_data, filename, user_id, voice_name=None, language="pl", service=None):
        """
        Clone a voice using the preferred service
        
        Args:
            file_data: File-like object containing audio data
            filename: Original filename
            user_id: ID of the user who owns this voice
            voice_name: Name for the voice
            language: Language code
            service: Override the service to use
            
        Returns:
            tuple: (success, data/error message)
        """
        if service is None:
            service = VoiceService.get_active_service()
            
        # Ensure the service is available
        if not VoiceService.is_service_available(service):
            available_service = (
                VoiceService.CARTESIA if service == VoiceService.ELEVENLABS and 
                VoiceService.is_service_available(VoiceService.CARTESIA) 
                else VoiceService.ELEVENLABS
            )
            
            if VoiceService.is_service_available(available_service):
                logger.warning(f"Service {service} not available, falling back to {available_service}")
                service = available_service
            else:
                return False, f"No voice services available. Please configure API keys."
        
        try:
            if service == VoiceService.ELEVENLABS:
                # ElevenLabs expects files as a list of tuples, voice_name, voice_description
                from utils.audio_splitter import split_audio_file
                
                # Split audio into chunks if needed
                audio_chunks = split_audio_file(file_data, filename)
                
                # Set voice description
                voice_description = f"Voice for user {user_id}"
                
                return ElevenLabsService.clone_voice(
                    files=audio_chunks,
                    voice_name=voice_name or f"{user_id}_MAIN",
                    voice_description=voice_description
                )
            elif service == VoiceService.CARTESIA:
                # Cartesia takes a list of tuples for files
                # Reset file position to beginning
                file_data.seek(0)
                mime_type = "audio/wav" if filename.lower().endswith(".wav") else "audio/mpeg"
                files = [(filename, file_data, mime_type)]
                
                # Set a voice description for Cartesia
                voice_description = f"Voice for user {user_id}"
                
                return CartesiaSDKService.clone_voice(
                    files=files,
                    voice_name=voice_name or f"{user_id}_MAIN",
                    voice_description=voice_description,
                    language=language
                )
                
        except Exception as e:
            logger.error(f"Error cloning voice with {service}: {str(e)}")
            return False, f"Error with {service}: {str(e)}"
    
    @staticmethod
    def delete_voice(voice_id, external_voice_id, service=None):
        """
        Delete a voice using the preferred service
        
        Args:
            voice_id: Database ID of the voice
            external_voice_id: External service voice ID (e.g., elevenlabs_voice_id or cartesia_voice_id)
            service: Override the service to use
            
        Returns:
            tuple: (success, message)
        """
        if service is None:
            service = VoiceService.get_active_service()
        
        if not VoiceService.is_service_available(service):
            return False, f"Service {service} not available"
        
        try:
            if service == VoiceService.ELEVENLABS:
                return ElevenLabsService.delete_voice(external_voice_id)
            elif service == VoiceService.CARTESIA:
                return CartesiaSDKService.delete_voice(external_voice_id)
                
        except Exception as e:
            logger.error(f"Error deleting voice with {service}: {str(e)}")
            return False, f"Error with {service}: {str(e)}"
    
    @staticmethod
    def synthesize_speech(external_voice_id, text, language="pl", service=None):
        """
        Synthesize speech using the preferred service
        
        Args:
            external_voice_id: External service voice ID
            text: Text to synthesize
            language: Language code
            service: Override the service to use
            
        Returns:
            tuple: (success, audio_data/error message)
        """
        if service is None:
            service = VoiceService.get_active_service()
        
        if not VoiceService.is_service_available(service):
            return False, f"Service {service} not available"
        
        try:
            if service == VoiceService.ELEVENLABS:
                return ElevenLabsService.synthesize_speech(external_voice_id, text)
            elif service == VoiceService.CARTESIA:
                # Default to Sonic-2 model for Cartesia
                return CartesiaSDKService.synthesize_speech(
                    external_voice_id, 
                    text, 
                    language=language
                )
                
        except Exception as e:
            logger.error(f"Error synthesizing speech with {service}: {str(e)}")
            return False, f"Error with {service}: {str(e)}" 