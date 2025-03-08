from models.voice_model import VoiceModel
from models.audio_model import AudioModel
from config import Config

class VoiceController:
    """Controller for voice-related operations"""
    
    @staticmethod
    def clone_voice(file):
        """
        Process voice cloning request
        
        Args:
            file: File object from request
            
        Returns:
            tuple: (success, data/error_message, status_code)
        """
        if not file or file.filename == '':
            return False, "No file provided", 400
            
        # Check file extension
        if not VoiceController.allowed_file(file.filename):
            return False, "Invalid file type", 400
            
        # Clone voice
        success, result = VoiceModel.clone_voice(file.stream, file.filename)
        
        if success:
            return True, {"voice_id": result["voice_id"], "name": Config.VOICE_NAME}, 200
        else:
            return False, result, 500
    
    @staticmethod
    def delete_voice(voice_id):
        """
        Process voice deletion request
        
        Args:
            voice_id: ID of the voice to delete
            
        Returns:
            tuple: (success, message, status_code)
        """
        # Delete voice from ElevenLabs
        success, message = VoiceModel.delete_voice(voice_id)
        
        if not success:
            return False, {"error": "Failed to delete voice", "details": message}, 500
            
        # Delete associated audio files from S3
        audio_success, audio_message = AudioModel.delete_voice_audio(voice_id)
        
        if not audio_success:
            return True, {"message": "Voice deleted, but failed to delete some audio files", "details": audio_message}, 200
            
        return True, {"message": "Voice and associated files deleted"}, 200
    
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