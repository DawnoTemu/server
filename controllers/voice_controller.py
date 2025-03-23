from models.voice_model import VoiceModel
from models.audio_model import AudioModel
from config import Config

class VoiceController:
    """Controller for voice-related operations"""
    
    @staticmethod
    def clone_voice(file, user_id, voice_name=None):
        """
        Process voice cloning request
        
        Args:
            file: File object from request
            user_id: ID of the user who owns this voice
            voice_name: Optional name for the voice
            
        Returns:
            tuple: (success, data/error_message, status_code)
        """
        if not file or file.filename == '':
            return False, {"error": "No file provided"}, 400
            
        # Check file extension
        if not VoiceController.allowed_file(file.filename):
            return False, {"error": "Invalid file type"}, 400
            
        # Clone voice with background noise removal (this can help with audio clarity)
        success, result = VoiceModel.clone_voice(
            file.stream, 
            file.filename, 
            user_id,
            voice_name=voice_name
        )
        
        if success:
            return True, result, 200
        else:
            return False, {"error": result}, 500
    
    @staticmethod
    def delete_voice(voice_id):
        """
        Process voice deletion request
        
        Args:
            voice_id: ID of the voice to delete
            
        Returns:
            tuple: (success, message, status_code)
        """
        # Delete voice using the VoiceModel
        success, message = VoiceModel.delete_voice(voice_id)
        
        if not success:
            return False, {"error": "Failed to delete voice", "details": message}, 500
            
        # Delete associated audio files from S3
        voice = VoiceModel.get_voice_by_id(voice_id)
        if voice:
            audio_success, audio_message = AudioModel.delete_voice_audio(voice.elevenlabs_voice_id)
            
            if not audio_success:
                return True, {"message": "Voice deleted, but failed to delete some audio files", "details": audio_message}, 200
        
        return True, {"message": "Voice and associated files deleted"}, 200
    
    @staticmethod
    def get_voices_by_user(user_id):
        """
        Get all voices owned by a user
        
        Args:
            user_id: ID of the user
            
        Returns:
            tuple: (success, data/error_message, status_code)
        """
        try:
            voices = VoiceModel.get_voices_by_user(user_id)
            
            return True, [voice.to_dict() for voice in voices], 200
        except Exception as e:
            return False, {"error": str(e)}, 500
    
    @staticmethod
    def get_voice(voice_id):
        """
        Get a specific voice by ID
        
        Args:
            voice_id: ID of the voice
            
        Returns:
            tuple: (success, data/error_message, status_code)
        """
        try:
            voice = VoiceModel.get_voice_by_id(voice_id)
            
            if not voice:
                return False, {"error": "Voice not found"}, 404
                
            return True, voice.to_dict(), 200
        except Exception as e:
            return False, {"error": str(e)}, 500
    
    @staticmethod
    def get_voice_sample_url(voice_id):
        """
        Get the voice sample URL
        
        Args:
            voice_id: ID of the voice
            
        Returns:
            tuple: (success, data/error_message, status_code)
        """
        success, result = VoiceModel.get_sample_url(voice_id)
        
        if not success:
            return False, {"error": result}, 404
            
        return True, {"url": result}, 200
    
    @staticmethod
    def allowed_file(filename):
        """
        Check if a file has an allowed extension
        
        Args:
            filename: Name of the file to check
            
        Returns:
            bool: True if file is allowed, False otherwise
        """
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS