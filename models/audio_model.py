import requests
from io import BytesIO
from botocore.exceptions import ClientError
from utils.s3_client import S3Client
from config import Config
import logging

# Configure logger
logger = logging.getLogger('audio_model')

class AudioModel:
    """Model for audio synthesis and storage operations"""
    
    # Audio object key prefix
    VOICES_PREFIX = "voices/"
    
    # Content type mapping
    CONTENT_TYPES = {
        "mp3": "audio/mpeg",
        "wav": "audio/wav"
    }
    
    @staticmethod
    def get_object_key(voice_id, story_id, extension="mp3"):
        """Generate consistent S3 object key for voice/story audio"""
        return f"{AudioModel.VOICES_PREFIX}{voice_id}/{story_id}.{extension}"
    
    @staticmethod
    def synthesize_speech(voice_id, text):
        """
        Synthesize speech using ElevenLabs API
        
        Args:
            voice_id: ID of the voice to use
            text: Text to synthesize
            
        Returns:
            tuple: (success, audio_data/error message)
        """
        try:
            session = requests.Session()
            session.headers.update({"xi-api-key": Config.ELEVENLABS_API_KEY})
            
            # Use a session with keep-alive for better performance
            with session:
                response = session.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream",
                    json={
                        "text": text,
                        "model_id": "eleven_multilingual_v2",
                        "voice_settings": {
                            "stability": 0.45,
                            "similarity_boost": 0.85,
                            "style": 0.35,
                            "use_speaker_boost": True,
                            "speed": 1.2
                        }
                    },
                    headers={"Accept": "audio/mpeg"}
                )
                
                response.raise_for_status()
                return True, BytesIO(response.content)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error synthesizing speech: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                return False, e.response.json()
            return False, str(e)
        except Exception as e:
            logger.error(f"Unexpected error in synthesize_speech: {str(e)}")
            return False, str(e)
    
    @staticmethod
    def store_audio(audio_data, voice_id, story_id):
        """
        Store audio data in S3 with caching headers
        
        Args:
            audio_data: BytesIO object containing audio data
            voice_id: Voice ID
            story_id: Story ID
            
        Returns:
            tuple: (success, message)
        """
        try:
            # Get S3 key
            s3_key = AudioModel.get_object_key(voice_id, story_id)
            
            # Upload to S3 with enhanced settings
            extra_args = {
                'ContentType': AudioModel.CONTENT_TYPES.get("mp3", "audio/mpeg"),
                'CacheControl': 'max-age=86400',  # Cache for 24 hours
                'ContentDisposition': f'attachment; filename="{story_id}.mp3"'
            }
            
            # Use our optimized S3 client
            success = S3Client.upload_fileobj(audio_data, s3_key, extra_args)
            
            if success:
                return True, "Audio stored successfully"
            else:
                return False, "Failed to upload to S3"
                
        except Exception as e:
            logger.error(f"Error storing audio: {str(e)}")
            return False, str(e)
    
    @staticmethod
    def check_audio_exists(voice_id, story_id):
        """
        Check if audio exists in S3
        
        Args:
            voice_id: Voice ID
            story_id: Story ID
            
        Returns:
            bool: True if audio exists, False otherwise
        """
        try:
            s3_key = AudioModel.get_object_key(voice_id, story_id)
            
            # Use our optimized S3 client
            s3_client = S3Client.get_client()
            
            s3_client.head_object(
                Bucket=S3Client.get_bucket_name(),
                Key=s3_key
            )
            
            return True
        except ClientError:
            return False
    
    @staticmethod
    def get_audio_presigned_url(voice_id, story_id, expires_in=3600):
        """
        Generate a presigned URL for direct S3 access
        
        Args:
            voice_id: Voice ID
            story_id: Story ID
            expires_in: URL expiration time in seconds (default: 1 hour)
            
        Returns:
            tuple: (success, url/error message)
        """
        try:
            # First check if the audio file exists
            if not AudioModel.check_audio_exists(voice_id, story_id):
                return False, "Audio file does not exist"
                
            # Generate presigned URL
            s3_key = AudioModel.get_object_key(voice_id, story_id)
            
            response_headers = {
                'ResponseContentType': 'audio/mpeg',
                'ResponseContentDisposition': f'attachment; filename="{story_id}.mp3"'
            }
            
            # Use our optimized S3 client
            presigned_url = S3Client.generate_presigned_url(
                s3_key, 
                expires_in, 
                response_headers
            )
            
            return True, presigned_url
            
        except Exception as e:
            logger.error(f"Error generating presigned URL: {str(e)}")
            return False, str(e)
    
    @staticmethod
    def delete_voice_audio(voice_id):
        """
        Delete all audio files for a voice
        
        Args:
            voice_id: Voice ID
            
        Returns:
            tuple: (success, message)
        """
        try:
            s3_client = S3Client.get_client()
            
            # List objects to delete
            paginator = s3_client.get_paginator('list_objects_v2')
            
            # Collect all keys to delete
            keys_to_delete = []
            prefix = f"{AudioModel.VOICES_PREFIX}{voice_id}/"
            
            for page in paginator.paginate(
                Bucket=S3Client.get_bucket_name(), 
                Prefix=prefix
            ):
                if 'Contents' in page:
                    keys_to_delete.extend([obj['Key'] for obj in page['Contents']])
            
            # If no objects found, return success
            if not keys_to_delete:
                return True, "No audio files found to delete"
            
            # Use our optimized batch delete
            success, deleted_count, errors = S3Client.delete_objects(keys_to_delete)
            
            if success:
                return True, f"Deleted {deleted_count} audio files"
            else:
                logger.warning(f"Partial success deleting audio files: {deleted_count} deleted with {len(errors)} errors")
                return False, f"Failed to delete some audio files: {errors[:3]}"
                
        except Exception as e:
            logger.error(f"Error deleting audio files: {str(e)}")
            return False, str(e)