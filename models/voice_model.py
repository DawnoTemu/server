import requests
from io import BytesIO
import logging
import os
import sys

from config import Config
from database import db
from datetime import datetime

# Configure logger
logger = logging.getLogger('voice_model_service')

class Voice(db.Model):
    """Database model for voice recordings"""
    __tablename__ = 'voices'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    elevenlabs_voice_id = db.Column(db.String(255), nullable=False, unique=True)
    s3_sample_key = db.Column(db.String(512), nullable=True)  # S3 key for the original sample
    sample_filename = db.Column(db.String(255), nullable=True)
    
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
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
class VoiceModel:
    """Model for voice cloning operations"""
    
    # Audio sample object key prefix
    VOICE_SAMPLES_PREFIX = "voice_samples/"
    
    @staticmethod
    def create_api_session():
        """Create a session for ElevenLabs API with authentication"""
        session = requests.Session()
        session.headers.update({"xi-api-key": Config.ELEVENLABS_API_KEY})
        return session
    
    @staticmethod
    def clone_voice(file_data, filename, user_id, voice_name=None, remove_background_noise=False):
        """
        Clone a voice using ElevenLabs API and store in database
        
        Args:
            file_data: File-like object containing audio data
            filename: Original filename
            user_id: ID of the user who owns this voice
            voice_name: Name for the voice (defaults to Config.VOICE_NAME)
            remove_background_noise: Whether to remove background noise (default: False)
            
        Returns:
            tuple: (success, data/error message)
        """
        try:
            # Import audio_splitter here to avoid circular imports
            from utils.audio_splitter import split_audio_file
            from utils.s3_client import S3Client
            
            session = VoiceModel.create_api_session()
            
            # Use provided voice name or default
            if not voice_name:
                voice_name = Config.VOICE_NAME
            
            # Split audio into chunks if needed
            audio_chunks = split_audio_file(file_data, filename)
            logger.info(f"Split audio into {len(audio_chunks)} chunks")
            
            # Prepare multipart form data
            files = []
            
            # Add each audio chunk as a file with the same field name
            for chunk_filename, chunk_file, mime_type in audio_chunks:
                files.append(("files", (chunk_filename, chunk_file, mime_type)))
            
            # Add other form fields
            files.append(("name", (None, voice_name)))
            files.append(("description", (None, f"Voice cloned for user {user_id}")))
            files.append(("remove_background_noise", (None, str(remove_background_noise).lower())))
            
            # Make API request
            response = session.post(
                "https://api.elevenlabs.io/v1/voices/add",
                files=files
            )
            
            if response.status_code == 200:
                # Get the ElevenLabs voice ID from response
                elevenlabs_data = response.json()
                elevenlabs_voice_id = elevenlabs_data.get("voice_id")
                
                if not elevenlabs_voice_id:
                    logger.error("ElevenLabs API did not return a voice_id")
                    return False, "Voice cloning failed: No voice ID returned"
                
                # Store original sample in S3
                s3_sample_key = None
                try:
                    # Reset the first chunk's file position
                    first_chunk_filename = audio_chunks[0][0]
                    first_chunk_file = audio_chunks[0][1]
                    first_chunk_file.seek(0)
                    
                    # Generate S3 key for the sample
                    s3_sample_key = f"{VoiceModel.VOICE_SAMPLES_PREFIX}{user_id}/{elevenlabs_voice_id}.mp3"
                    
                    # Upload to S3
                    extra_args = {
                        'ContentType': 'audio/mpeg',
                        'CacheControl': 'max-age=31536000',  # Cache for 1 year
                    }
                    
                    S3Client.upload_fileobj(first_chunk_file, s3_sample_key, extra_args)
                    logger.info(f"Stored voice sample in S3: {s3_sample_key}")
                except Exception as e:
                    logger.error(f"Failed to store voice sample in S3: {str(e)}")
                    # Continue even if S3 storage fails
                
                # Create and save a new Voice record in the database
                new_voice = Voice(
                    name=voice_name,
                    elevenlabs_voice_id=elevenlabs_voice_id,
                    user_id=user_id,
                    s3_sample_key=s3_sample_key,
                    sample_filename=first_chunk_filename if audio_chunks else filename
                )
                
                db.session.add(new_voice)
                db.session.commit()
                
                logger.info(f"Voice cloned and stored in database: {new_voice}")
                
                return True, {
                    "voice_id": elevenlabs_voice_id,
                    "name": voice_name,
                    "id": new_voice.id
                }
            else:
                error_detail = "Cloning failed"
                try:
                    error_detail = response.json().get("detail", error_detail)
                except:
                    pass
                logger.error(f"ElevenLabs API error: {response.status_code} - {error_detail}")
                return False, error_detail
                
        except Exception as e:
            logger.error(f"Exception in clone_voice: {str(e)}")
            return False, str(e)
    
    @staticmethod
    def delete_voice(voice_id):
        """
        Delete a voice from ElevenLabs and from the database
        
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
            
            # Get the ElevenLabs voice ID
            elevenlabs_voice_id = voice.elevenlabs_voice_id
            
            # Delete the voice from ElevenLabs
            session = VoiceModel.create_api_session()
            api_success = True
            api_message = "Voice deleted from ElevenLabs"
            
            try:
                # Make API request
                response = session.delete(
                    f"https://api.elevenlabs.io/v1/voices/{elevenlabs_voice_id}"
                )
                
                if response.status_code != 200:
                    api_success = False
                    api_message = response.json().get("detail", "Deletion failed")
                    logger.error(f"ElevenLabs API error: {response.status_code} - {api_message}")
            except Exception as e:
                api_success = False
                api_message = str(e)
                logger.error(f"Exception deleting from ElevenLabs: {str(e)}")
            
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
                return True, f"Voice deleted from database and ElevenLabs, but there was an issue with S3: {s3_message}"
            elif s3_success:
                return True, f"Voice deleted from database and S3, but there was an issue with ElevenLabs: {api_message}"
            else:
                return True, f"Voice deleted from database, but there were issues with ElevenLabs ({api_message}) and S3 ({s3_message})"
                
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
                
            url = S3Client.generate_presigned_url(
                voice.s3_sample_key,
                expires_in,
                {'ResponseContentType': 'audio/mpeg'}
            )
            
            return True, url
        except Exception as e:
            logger.error(f"Exception getting sample URL: {str(e)}")
            return False, str(e)