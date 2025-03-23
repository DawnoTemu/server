from models.audio_model import AudioModel
from models.story_model import StoryModel
from models.voice_model import VoiceModel
from config import Config
import logging

# Configure logger
logger = logging.getLogger('audio_controller')

class AudioController:
    """Controller for audio-related operations"""
    
    @staticmethod
    def check_audio_exists(voice_id, story_id):
        """
        Check if audio exists for a voice and story
        
        Args:
            voice_id: Voice ID
            story_id: Story ID
            
        Returns:
            tuple: (success, data, status_code)
        """
        try:
            exists = AudioModel.check_audio_exists(voice_id, story_id)
            return True, {"exists": exists}, 200
        except Exception as e:
            logger.error(f"Error checking if audio exists: {str(e)}")
            return False, {"error": str(e)}, 500
    
    @staticmethod
    def get_audio(voice_id, story_id, range_header=None):
        """
        Get audio data for a voice and story
        
        Args:
            voice_id: Voice ID
            story_id: Story ID
            range_header: Optional HTTP Range header
            
        Returns:
            tuple: (success, audio_data/error message, status_code, extra_info)
        """
        try:
            success, data, extra = AudioModel.get_audio(voice_id, story_id, range_header)
            
            if not success:
                return False, {"error": str(data)}, 404, None
                
            # Status code is 206 for partial content (if range header was provided)
            status_code = 206 if range_header else 200
            
            return True, data, status_code, extra
        except Exception as e:
            logger.error(f"Error retrieving audio: {str(e)}")
            return False, {"error": f"Failed to retrieve audio: {str(e)}"}, 500, None
    
    @staticmethod
    def get_audio_presigned_url(voice_id, story_id, expires_in=3600):
        """
        Get a presigned URL for direct S3 access
        
        Args:
            voice_id: Voice ID
            story_id: Story ID
            expires_in: URL expiration time in seconds (default: 1 hour)
            
        Returns:
            tuple: (success, url/error message, status_code)
        """
        try:
            # First check if audio exists
            success, result, status = AudioController.check_audio_exists(voice_id, story_id)
            
            if not success or not result.get('exists', False):
                return False, "Audio not found", 404
                
            # Generate presigned URL
            success, result = AudioModel.get_audio_presigned_url(voice_id, story_id, expires_in)
            
            if not success:
                return False, {"error": f"Failed to generate presigned URL: {result}"}, 500
                
            return True, result, 200
        except Exception as e:
            logger.error(f"Error generating audio URL: {str(e)}")
            return False, {"error": f"Failed to generate audio URL: {str(e)}"}, 500

    @staticmethod
    def synthesize_audio(voice_id, story_id):
        """
        Synthesize audio for a story with a given voice
        
        Args:
            voice_id: ElevenLabs voice ID
            story_id: Story ID
            
        Returns:
            tuple: (success, data/error message, status_code)
        """
        try:
            # Get story text
            story = StoryModel.get_story_by_id(story_id)
            
            if not story:
                return False, {"error": "Story not found"}, 404
                
            text = story.get("content")
            
            if not text:
                return False, {"error": "Story text not found in story"}, 400
                
            # Synthesize speech
            synth_success, result = AudioModel.synthesize_speech(voice_id, text)
            
            if not synth_success:
                return False, {"error": f"Synthesis failed: {result}"}, 500
                
            # Store audio in S3
            store_success, message = AudioModel.store_audio(result, voice_id, story_id)
            
            if not store_success:
                return False, {"error": f"Storage failed: {message}"}, 500
                
            # Generate presigned URL for the audio
            presigned_success, presigned_url = AudioModel.get_audio_presigned_url(voice_id, story_id)
            
            if not presigned_success:
                return False, {"error": f"Failed to generate URL: {presigned_url}"}, 500
                
            return True, {"status": "success", "url": presigned_url}, 200
            
        except Exception as e:
            logger.error(f"Error synthesizing audio: {str(e)}")
            return False, {"error": str(e)}, 500