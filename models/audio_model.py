import requests
from io import BytesIO
from botocore.exceptions import ClientError
from config import Config

class AudioModel:
    """Model for audio synthesis and storage operations"""
    
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
            if hasattr(e, 'response') and e.response is not None:
                return False, e.response.json()
            return False, str(e)
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def store_audio(audio_data, voice_id, story_id):
        """
        Store audio data in S3
        
        Args:
            audio_data: BytesIO object containing audio data
            voice_id: Voice ID
            story_id: Story ID
            
        Returns:
            tuple: (success, message)
        """
        try:
            s3_client = Config.get_s3_client()
            s3_key = f"{voice_id}/{story_id}.mp3"
            
            # Upload to S3
            s3_client.upload_fileobj(
                audio_data,
                Config.S3_BUCKET,
                s3_key,
                ExtraArgs={'ContentType': 'audio/mpeg'}
            )
            
            return True, "Audio stored successfully"
        except Exception as e:
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
            s3_client = Config.get_s3_client()
            s3_key = f"{voice_id}/{story_id}.mp3"
            
            s3_client.head_object(
                Bucket=Config.S3_BUCKET,
                Key=s3_key
            )
            
            return True
        except ClientError:
            return False
    
    @staticmethod
    def get_audio(voice_id, story_id, range_header=None):
        """
        Get audio data from S3
        
        Args:
            voice_id: Voice ID
            story_id: Story ID
            range_header: Optional HTTP Range header
            
        Returns:
            tuple: (success, data/error message, extra info)
        """
        try:
            s3_client = Config.get_s3_client()
            s3_key = f"{voice_id}/{story_id}.mp3"
            
            s3_kwargs = {'Bucket': Config.S3_BUCKET, 'Key': s3_key}
            if range_header:
                s3_kwargs['Range'] = range_header
            
            s3_response = s3_client.get_object(**s3_kwargs)
            
            # Get audio data
            data = s3_response['Body'].read()
            
            # Determine if partial content (206) response is needed
            status_code = 206 if range_header else 200
            
            # Extra information for response headers
            extra = {
                'content_length': s3_response['ContentLength'],
                'content_range': s3_response.get('ContentRange')
            }
            
            return True, data, extra
            
        except ClientError as e:
            return False, str(e), None
        except Exception as e:
            return False, str(e), None
    
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
            s3_client = Config.get_s3_client()
            
            # List objects to delete
            paginator = s3_client.get_paginator('list_objects_v2')
            objects_to_delete = []
            
            for page in paginator.paginate(Bucket=Config.S3_BUCKET, Prefix=f"{voice_id}/"):
                if 'Contents' in page:
                    objects_to_delete.extend([{'Key': obj['Key']} for obj in page['Contents']])
            
            # Delete objects if any were found
            if objects_to_delete:
                s3_client.delete_objects(
                    Bucket=Config.S3_BUCKET,
                    Delete={'Objects': objects_to_delete}
                )
            
            return True, f"Deleted {len(objects_to_delete)} audio files"
        except Exception as e:
            return False, str(e)