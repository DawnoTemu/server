import requests
from io import BytesIO
import logging
import os
import sys
import uuid
import tempfile

from config import Config
from database import db
from datetime import datetime
from utils.voice_service import VoiceService

# Configure logger
logger = logging.getLogger('voice_model_service')

# Voice status constants (enum-like)
class VoiceStatus:
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"

class Voice(db.Model):
    """Database model for voice recordings"""
    __tablename__ = 'voices'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    elevenlabs_voice_id = db.Column(db.String(255), nullable=True, unique=True)  # Now nullable while pending
    s3_sample_key = db.Column(db.String(512), nullable=True)  # S3 key for the original sample
    sample_filename = db.Column(db.String(255), nullable=True)
    
    # Status tracking for async processing
    status = db.Column(db.String(20), nullable=False, default=VoiceStatus.PENDING)
    error_message = db.Column(db.Text, nullable=True)
    
    # Foreign key to user table
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Relationship with User model
    user = db.relationship('User', backref=db.backref('voices', lazy=True))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<Voice {self.id}: {self.name} (ElevenLabs ID: {self.elevenlabs_voice_id})>"
    
    def to_dict(self):
        """Convert voice to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'elevenlabs_voice_id': self.elevenlabs_voice_id,
            'user_id': self.user_id,
            'status': self.status,  # Include status in API response
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
class VoiceModel:
    """Model for voice cloning operations"""
    
    # Audio sample object key prefix
    VOICE_SAMPLES_PREFIX = "voice_samples/"
    
    @staticmethod
    def create_api_session():
        """Create a session for voice API with authentication"""
        # For backward compatibility, we still provide this method
        # but it now routes to the appropriate service
        if Config.PREFERRED_VOICE_SERVICE == "cartesia":
            from utils.cartesia_sdk_service import CartesiaSDKService
            return CartesiaSDKService.get_client()
        else:
            from utils.elevenlabs_service import ElevenLabsService
            return ElevenLabsService.create_session()
    
    @staticmethod
    def clone_voice(file_data, filename, user_id, voice_name=None):
        """
        Create a voice record and queue an async job for voice cloning
        
        Args:
            file_data: File-like object containing audio data
            filename: Original filename
            user_id: ID of the user who owns this voice
            voice_name: Name for the voice (defaults to Config.VOICE_NAME)
            
        Returns:
            tuple: (success, data/error message)
        """
        try:
            # Set voice name and description
            if not voice_name:               
                voice_name = f"{user_id}_MAIN"
            
            # Create a voice record with pending status
            new_voice = Voice(
                name=voice_name,
                user_id=user_id,
                status=VoiceStatus.PENDING,
                elevenlabs_voice_id=None  # Will be set when async task completes
            )
            
            db.session.add(new_voice)
            db.session.commit()
            
            # Save file data temporarily (Celery can't serialize file objects)
            temp_dir = tempfile.mkdtemp(prefix="storyvoice_")
            temp_path = os.path.join(temp_dir, f"voice_{new_voice.id}_{uuid.uuid4()}.tmp")
            
            # Reset file position and save
            file_data.seek(0)
            with open(temp_path, 'wb') as f:
                f.write(file_data.read())
            
            # Queue async task
            from tasks.voice_tasks import clone_voice_task
            task = clone_voice_task.delay(new_voice.id, temp_path, filename, user_id, voice_name)
            
            logger.info(f"Queued voice cloning task {task.id} for voice ID {new_voice.id}")
            
            # Return voice ID and status
            return True, {
                "id": new_voice.id,
                "name": voice_name,
                "status": VoiceStatus.PENDING
            }
                
        except Exception as e:
            logger.error(f"Exception in clone_voice: {str(e)}")
            
            # If we have created a voice record but failed to queue the task,
            # update its status to ERROR
            if 'new_voice' in locals() and new_voice.id:
                try:
                    new_voice.status = VoiceStatus.ERROR
                    new_voice.error_message = str(e)
                    db.session.commit()
                except:
                    pass  # Don't let this cause another exception
                    
            return False, str(e)
    
    @staticmethod
    def _clone_voice_api(file_data, filename, user_id, voice_name=None, remove_background_noise=False):
        """
        Internal method to handle the actual API call for voice cloning
        This is called by the async task, not directly by controllers
        
        Args:
            file_data: File-like object containing audio data
            filename: Original filename
            user_id: ID of the user who owns this voice
            voice_name: Name for the voice
            remove_background_noise: Whether to remove background noise
            
        Returns:
            tuple: (success, data/error message)
        """
        try:
            # Import audio_splitter here to avoid circular imports
            from utils.audio_splitter import split_audio_file
            from utils.s3_client import S3Client
            
            # Set voice name
            if not voice_name:               
                voice_name = f"{user_id}_MAIN"
            
            # Get the language from config - default to 'pl' if not specified
            language = getattr(Config, 'DEFAULT_LANGUAGE', 'pl')
            
            # For ElevenLabs, we need to split the audio
            if Config.PREFERRED_VOICE_SERVICE == "elevenlabs":
                # Split audio into chunks if needed
                audio_chunks = split_audio_file(file_data, filename)
                logger.info(f"Split audio into {len(audio_chunks)} chunks")
                
                # Use the ElevenLabsService through VoiceService
                return VoiceService.clone_voice(
                    file_data=file_data,
                    filename=filename,
                    user_id=user_id,
                    voice_name=voice_name,
                    service="elevenlabs"
                )
            else:
                # Use the CartesiaService through VoiceService
                return VoiceService.clone_voice(
                    file_data=file_data,
                    filename=filename,
                    user_id=user_id,
                    voice_name=voice_name,
                    language=language,
                    service="cartesia"
                )
                
        except Exception as e:
            logger.error(f"Exception in _clone_voice_api: {str(e)}")
            return False, str(e)
    
    @staticmethod
    def delete_voice(voice_id):
        """
        Delete a voice from the external service and from the database
        
        Args:
            voice_id: Database ID of the voice
            
        Returns:
            tuple: (success, message)
        """
        try:
            # Get the voice from the database
            voice = Voice.query.get(voice_id)
            
            if not voice:
                return False, "Voice not found in database"
            
            # Check if the voice has an external ID (it might be in pending state)
            external_voice_id = voice.elevenlabs_voice_id
            api_success = True
            api_message = "Voice was still pending, no external voice to delete"
            
            if external_voice_id:
                # Delete the voice from the external service
                api_success, api_message = VoiceService.delete_voice(
                    voice_id=voice_id,
                    external_voice_id=external_voice_id
                )
            
            # Delete any S3 samples
            s3_success = True
            s3_message = "Voice sample deleted from S3"
            
            if voice.s3_sample_key:
                try:
                    from utils.s3_client import S3Client
                    S3Client.delete_objects([voice.s3_sample_key])
                except Exception as e:
                    s3_success = False
                    s3_message = str(e)
                    logger.error(f"Exception deleting S3 sample: {str(e)}")
            
            # Delete the voice from the database
            db.session.delete(voice)
            db.session.commit()
            
            # Determine overall success and message
            if api_success and s3_success:
                return True, "Voice deleted successfully from all systems"
            elif api_success:
                return True, f"Voice deleted from database and external service, but there was an issue with S3: {s3_message}"
            elif s3_success:
                return True, f"Voice deleted from database and S3, but there was an issue with external service: {api_message}"
            else:
                return True, f"Voice deleted from database, but there were issues with external service ({api_message}) and S3 ({s3_message})"
                
        except Exception as e:
            logger.error(f"Exception in delete_voice: {str(e)}")
            db.session.rollback()
            return False, str(e)
    
    @staticmethod
    def get_voices_by_user(user_id):
        """
        Get all voices owned by a specific user
        
        Args:
            user_id: ID of the user
            
        Returns:
            list: List of Voice objects
        """
        return Voice.query.filter_by(user_id=user_id).all()
    
    @staticmethod
    def get_voice_by_id(voice_id):
        """
        Get a voice by ID
        
        Args:
            voice_id: ID of the voice
            
        Returns:
            Voice: Voice object or None
        """
        return Voice.query.get(voice_id)
    
    @staticmethod
    def get_voice_by_elevenlabs_id(elevenlabs_voice_id):
        """
        Get a voice by ElevenLabs voice ID
        
        Args:
            elevenlabs_voice_id: ElevenLabs voice ID
            
        Returns:
            Voice: Voice object or None
        """
        return Voice.query.filter_by(elevenlabs_voice_id=elevenlabs_voice_id).first()
    
    @staticmethod
    def get_sample_url(voice_id, expires_in=3600):
        """
        Get a presigned URL for the voice sample
        
        Args:
            voice_id: ID of the voice
            expires_in: URL expiration time in seconds
            
        Returns:
            tuple: (success, url/error message)
        """
        try:
            from utils.s3_client import S3Client
            
            voice = Voice.query.get(voice_id)
            if not voice or not voice.s3_sample_key:
                return False, "Voice sample not found"
                
            # Check if voice is ready
            if voice.status != VoiceStatus.READY:
                return False, f"Voice is not ready (status: {voice.status})"
                
            url = S3Client.generate_presigned_url(
                voice.s3_sample_key,
                expires_in,
                {'ResponseContentType': 'audio/mpeg'}
            )
            
            return True, url
        except Exception as e:
            logger.error(f"Exception getting sample URL: {str(e)}")
            return False, str(e)