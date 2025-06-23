import requests
from io import BytesIO
from botocore.exceptions import ClientError
from enum import Enum
import logging
import os
from datetime import datetime

from database import db
from utils.s3_client import S3Client
from config import Config
from utils.voice_service import VoiceService

# Configure logger
logger = logging.getLogger('audio_model')

class AudioStatus(Enum):
    """Enumeration of possible audio story statuses"""
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"


class AudioStory(db.Model):
    """Database model for voice story audio"""
    __tablename__ = 'audio_stories'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign keys
    story_id = db.Column(db.Integer, db.ForeignKey('stories.id'), nullable=False)
    voice_id = db.Column(db.Integer, db.ForeignKey('voices.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Relationships
    story = db.relationship('Story', backref=db.backref('audio_stories', lazy=True))
    voice = db.relationship('Voice', backref=db.backref('audio_stories', lazy=True))
    user = db.relationship('User', backref=db.backref('audio_stories', lazy=True))
    
    # Status
    status = db.Column(db.String(20), nullable=False, default=AudioStatus.PENDING.value)
    error_message = db.Column(db.Text, nullable=True)
    
    # S3 storage information
    s3_key = db.Column(db.String(512), nullable=True)
    duration_seconds = db.Column(db.Float, nullable=True)
    file_size_bytes = db.Column(db.Integer, nullable=True)
    
    # Metadata and tracking
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<AudioStory {self.id}: Story {self.story_id}, Voice {self.voice_id}>"
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        voice_name = self.voice.name if self.voice else None
        story_title = self.story.title if self.story else None
        
        return {
            'id': self.id,
            'story_id': self.story_id,
            'story_title': story_title,
            'voice_id': self.voice_id,
            'voice_name': voice_name,
            'user_id': self.user_id,
            'status': self.status,
            'error_message': self.error_message,
            'duration_seconds': self.duration_seconds,
            'file_size_bytes': self.file_size_bytes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class AudioModel:
    """Model for audio synthesis and storage operations"""
    
    # Audio object key prefix
    AUDIO_STORIES_PREFIX = "audio_stories/"
    
    # Content type mapping
    CONTENT_TYPES = {
        "mp3": "audio/mpeg",
        "wav": "audio/wav"
    }

    @staticmethod
    def get_object_key(voice_id, story_id, extension="mp3"):
        """Generate consistent S3 object key for voice/story audio"""
        # Use a new prefix to avoid conflicts with old files
        return f"{AudioModel.AUDIO_STORIES_PREFIX}{voice_id}/{story_id}.{extension}"
    
    @staticmethod
    def find_or_create_audio_record(story_id, voice_id, user_id):
        """
        Find or create an audio record in the database
        
        Args:
            story_id: ID of the story
            voice_id: ID of the voice in our database
            user_id: ID of the user
            
        Returns:
            AudioStory: Audio story record
        """
        try:
            # Check if a record already exists
            audio = AudioStory.query.filter_by(story_id=story_id, voice_id=voice_id).first()
            
            if audio:
                return audio
            
            # Create a new record
            audio = AudioStory(
                story_id=story_id,
                voice_id=voice_id,
                user_id=user_id,
                status=AudioStatus.PENDING.value
            )
            
            db.session.add(audio)
            db.session.commit()
            
            logger.info(f"Created new audio story record: id={audio.id}, story={story_id}, voice={voice_id}")
            return audio
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating audio story record: {str(e)}")
            raise
    
    @staticmethod
    def synthesize_speech(elevenlabs_voice_id, text):
        """
        Synthesize speech using external voice API
        
        Args:
            elevenlabs_voice_id: External voice ID
            text: Text to synthesize
            
        Returns:
            tuple: (success, audio_data/error message)
        """
        # Determine language - use default if not specified
        language = getattr(Config, 'DEFAULT_LANGUAGE', 'pl')
        
        # Use the unified VoiceService
        return VoiceService.synthesize_speech(
            external_voice_id=elevenlabs_voice_id,
            text=text,
            language=language
        )
    
    @staticmethod
    def store_audio(audio_data, voice_id, story_id, audio_record):
        """
        Store audio data in S3 and update database record
        
        Args:
            audio_data: BytesIO object containing audio data
            voice_id: Voice ID (database voice ID)
            story_id: Story ID
            audio_record: AudioStory record to update
            
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
                'ContentDisposition': f'attachment; filename="{story_id}_{voice_id}.mp3"'
            }
            
            # Reset file position
            audio_data.seek(0)
            
            # Get file size for metadata
            audio_data.seek(0, os.SEEK_END)
            file_size = audio_data.tell()
            audio_data.seek(0)
            
            # Use our optimized S3 client
            success = S3Client.upload_fileobj(audio_data, s3_key, extra_args)
            
            # Update database record
            if success:
                audio_record.s3_key = s3_key
                audio_record.file_size_bytes = file_size
                audio_record.status = AudioStatus.READY.value
                db.session.commit()
                logger.info(f"Updated audio record {audio_record.id} with S3 key {s3_key}")
                return True, "Audio stored successfully"
            else:
                # Update error status
                audio_record.status = AudioStatus.ERROR.value
                audio_record.error_message = "Failed to upload to S3"
                db.session.commit()
                return False, "Failed to upload to S3"
                
        except Exception as e:
            logger.error(f"Error storing audio: {str(e)}")
            
            # Update error status
            audio_record.status = AudioStatus.ERROR.value
            audio_record.error_message = str(e)
            db.session.commit()
            
            return False, str(e)
    
    @staticmethod
    def check_audio_exists(voice_id, story_id):
        """
        Check if audio exists in the database
        
        Args:
            voice_id: Voice ID
            story_id: Story ID
            
        Returns:
            bool: True if audio exists and is ready, False otherwise
        """
        try:
            # Only check the database - ignore any files created by the old system
            record = AudioStory.query.filter_by(
                voice_id=voice_id, 
                story_id=story_id, 
                status=AudioStatus.READY.value
            ).first()
            
            return record is not None and record.s3_key is not None
        except Exception as e:
            logger.error(f"Error checking if audio exists: {str(e)}")
            return False
    
    @staticmethod
    def get_audio(voice_id, story_id, range_header=None):
        """
        Get audio data from S3 for a database record
        
        Args:
            voice_id: Voice ID
            story_id: Story ID
            range_header: Optional HTTP Range header
            
        Returns:
            tuple: (success, data, extra_info)
        """
        try:
            # Find the database record
            record = AudioStory.query.filter_by(
                voice_id=voice_id, 
                story_id=story_id, 
                status=AudioStatus.READY.value
            ).first()
            
            if not record or not record.s3_key:
                return False, "Audio not found or not ready", None
            
            # Get the object from S3
            s3_client = S3Client.get_client()
            
            # Prepare get_object params
            get_params = {
                'Bucket': S3Client.get_bucket_name(),
                'Key': record.s3_key
            }
            
            # Add range header if provided
            if range_header:
                get_params['Range'] = range_header
            
            # Get the object
            response = s3_client.get_object(**get_params)
            
            # Get the content
            content = response['Body'].read()
            
            # Extra info for headers
            extra = {
                'content_length': response.get('ContentLength', len(content)),
                'content_type': response.get('ContentType', 'audio/mpeg')
            }
            
            # Add content range if available
            if 'ContentRange' in response:
                extra['content_range'] = response['ContentRange']
            
            return True, content, extra
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                return False, "Audio file not found in storage", None
            return False, f"S3 error: {error_code}", None
        except Exception as e:
            logger.error(f"Error retrieving audio: {str(e)}")
            return False, f"Unexpected error: {str(e)}", None
    
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
            # Find the database record
            record = AudioStory.query.filter_by(
                voice_id=voice_id, 
                story_id=story_id, 
                status=AudioStatus.READY.value
            ).first()
            
            if not record or not record.s3_key:
                return False, "Audio not found or not ready"
            
            # Generate presigned URL
            response_headers = {
                'ResponseContentType': 'audio/mpeg',
                'ResponseContentDisposition': f'attachment; filename="{story_id}_{voice_id}.mp3"'
            }
            
            # Use our optimized S3 client
            presigned_url = S3Client.generate_presigned_url(
                record.s3_key, 
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
            voice_id: Voice ID (database voice ID)
            
        Returns:
            tuple: (success, message)
        """
        try:
            # Get all audio records for this voice
            records = AudioStory.query.filter_by(voice_id=voice_id).all()
            
            if not records:
                return True, "No audio records found for this voice"
            
            # Collect S3 keys to delete
            keys_to_delete = []
            for record in records:
                if record.s3_key:
                    keys_to_delete.append(record.s3_key)
                
                # Delete the database record
                db.session.delete(record)
            
            # Commit database changes
            db.session.commit()
            
            # Delete S3 files if any
            if keys_to_delete:
                success, deleted_count, errors = S3Client.delete_objects(keys_to_delete)
                
                if not success:
                    logger.warning(f"Some S3 files couldn't be deleted: {errors}")
                    return True, f"Deleted database records but had issues with S3: {errors}"
                
                return True, f"Deleted {len(records)} audio records and {deleted_count} S3 files"
            
            return True, f"Deleted {len(records)} audio records (no S3 files)"
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting audio files: {str(e)}")
            return False, str(e)
    
    @staticmethod
    def synthesize_audio(voice_id, story_id, user_id, text):
        """
        Create or find an audio record and queue an async job to synthesize audio
        
        Args:
            voice_id: ID of the voice in the database
            story_id: ID of the story
            user_id: ID of the user
            text: Text to synthesize
            
        Returns:
            tuple: (success, data/error message)
        """
        try:
            # Find or create audio record
            audio_record = AudioModel.find_or_create_audio_record(story_id, voice_id, user_id)
            
            # Check if audio already exists and is ready
            if audio_record.status == AudioStatus.READY.value and audio_record.s3_key:
                # Generate a presigned URL
                success, url = AudioModel.get_audio_presigned_url(voice_id, story_id)
                
                if success:
                    return True, {"status": "ready", "url": url, "id": audio_record.id}
                else:
                    return False, {"error": "Failed to generate URL", "details": url}
            
            # If audio is already processing, just return the current status
            if audio_record.status == AudioStatus.PROCESSING.value:
                return True, {
                    "status": "processing", 
                    "id": audio_record.id,
                    "message": "Audio synthesis is already in progress"
                }
            
            # Update status to pending (for new or failed records)
            audio_record.status = AudioStatus.PENDING.value
            audio_record.error_message = None
            db.session.commit()
            
            # Queue async task
            from tasks.audio_tasks import synthesize_audio_task
            task = synthesize_audio_task.delay(audio_record.id, voice_id, story_id, text)
            
            logger.info(f"Queued audio synthesis task {task.id} for audio ID {audio_record.id}")
            
            # Return audio ID and status
            return True, {
                "status": "pending", 
                "id": audio_record.id,
                "message": "Audio synthesis has been queued"
            }
            
        except Exception as e:
            logger.error(f"Error in synthesize_audio: {str(e)}")
            
            # Update error status if record exists
            if 'audio_record' in locals() and audio_record:
                audio_record.status = AudioStatus.ERROR.value
                audio_record.error_message = str(e)
                db.session.commit()
                
            return False, {"error": str(e)}