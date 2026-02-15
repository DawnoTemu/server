import requests
from io import BytesIO
import logging
import os
import sys
import uuid
import tempfile
from typing import Any, Dict, Optional

from config import Config
from database import db
from datetime import datetime
from sqlalchemy import text
from utils.voice_service import VoiceService

# Configure logger
logger = logging.getLogger('voice_model_service')

# Voice status constants (enum-like)
class VoiceStatus:
    PENDING = "pending"
    PROCESSING = "processing"
    RECORDED = "recorded"
    READY = "ready"
    ERROR = "error"
    NEEDS_RERECORD = "needs_rerecord"


class VoiceAllocationStatus:
    """
    Slot lifecycle states. Transitions:
      RECORDED -> ALLOCATING -> READY -> RECORDED (on eviction)
    """
    RECORDED = "recorded"    # Voice sample stored, no remote slot allocated
    ALLOCATING = "allocating"  # Clone operation in progress with external API
    READY = "ready"          # Remote voice ID obtained, slot is active


class VoiceServiceProvider:
    ELEVENLABS = "elevenlabs"
    CARTESIA = "cartesia"


class VoiceSlotEventType:
    RECORDING_UPLOADED = "recording_uploaded"
    RECORDING_PROCESSING_QUEUED = "recording_processing_queued"
    RECORDING_PROCESSED = "recording_processed"
    RECORDING_PROCESSING_FAILED = "recording_processing_failed"
    ALLOCATION_QUEUED = "allocation_queued"
    ALLOCATION_STARTED = "allocation_started"
    ALLOCATION_COMPLETED = "allocation_completed"
    ALLOCATION_FAILED = "allocation_failed"
    SLOT_LOCK_ACQUIRED = "slot_lock_acquired"
    SLOT_LOCK_RELEASED = "slot_lock_released"
    SLOT_EVICTED = "slot_evicted"

class Voice(db.Model):
    """Database model for voice recordings"""
    __tablename__ = 'voices'
    __table_args__ = (
        db.Index(
            'ix_voices_elevenlabs_voice_id_populated',
            'elevenlabs_voice_id',
            unique=True,
            postgresql_where=text("elevenlabs_voice_id IS NOT NULL AND elevenlabs_voice_id <> ''"),
            sqlite_where=text("elevenlabs_voice_id IS NOT NULL AND elevenlabs_voice_id <> ''")
        ),
    )
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    elevenlabs_voice_id = db.Column(db.String(255), nullable=True)  # Nullable while pending
    s3_sample_key = db.Column(db.String(512), nullable=True)  # Permanent S3 key for the allocated sample
    sample_filename = db.Column(db.String(255), nullable=True)
    recording_s3_key = db.Column(db.String(512), nullable=True)  # Raw recording sample location
    recording_filesize = db.Column(db.BigInteger, nullable=True)
    
    # Status tracking for async processing
    status = db.Column(db.String(20), nullable=False, default=VoiceStatus.PENDING)
    allocation_status = db.Column(db.String(50), nullable=False, default=VoiceAllocationStatus.RECORDED)
    service_provider = db.Column(db.String(50), nullable=False, default=VoiceServiceProvider.ELEVENLABS)
    error_message = db.Column(db.Text, nullable=True)
    
    elevenlabs_allocated_at = db.Column(db.DateTime, nullable=True)
    last_used_at = db.Column(db.DateTime, nullable=True)
    slot_lock_expires_at = db.Column(db.DateTime, nullable=True)
    
    # Foreign key to user table
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Relationship with User model
    user = db.relationship('User', backref=db.backref('voices', lazy=True))
    slot_events = db.relationship(
        'VoiceSlotEvent',
        back_populates='voice',
        cascade='save-update, merge',
        passive_deletes=True,
        lazy=True
    )
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return (
            f"<Voice {self.id}: {self.name} "
            f"(status={self.status}, allocation_status={self.allocation_status}, "
            f"elevenlabs_id={self.elevenlabs_voice_id})>"
        )
    
    def to_dict(self):
        """Convert voice to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'elevenlabs_voice_id': self.elevenlabs_voice_id,
            'recording_s3_key': self.recording_s3_key,
            'recording_filesize': self.recording_filesize,
            'allocation_status': self.allocation_status,
            'service_provider': self.service_provider,
            'elevenlabs_allocated_at': self.elevenlabs_allocated_at.isoformat() if self.elevenlabs_allocated_at else None,
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None,
            'slot_lock_expires_at': self.slot_lock_expires_at.isoformat() if self.slot_lock_expires_at else None,
            'user_id': self.user_id,
            'status': self.status,
            'error_message': self.error_message,
            's3_sample_key': self.s3_sample_key,
            'sample_filename': self.sample_filename,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class VoiceSlotEvent(db.Model):
    """Audit log for voice slot lifecycle events."""
    __tablename__ = 'voice_slot_events'

    id = db.Column(db.Integer, primary_key=True)
    voice_id = db.Column(db.Integer, db.ForeignKey('voices.id', ondelete='SET NULL'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    event_type = db.Column(db.String(50), nullable=False)
    reason = db.Column(db.String(255), nullable=True)
    event_metadata = db.Column('metadata', db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    voice = db.relationship('Voice', back_populates='slot_events')
    user = db.relationship('User', backref=db.backref('voice_slot_events', lazy=True))

    def __repr__(self):
        return f"<VoiceSlotEvent {self.id}: voice={self.voice_id}, event={self.event_type}>"

    def to_dict(self):
        return {
            'id': self.id,
            'voice_id': self.voice_id,
            'user_id': self.user_id,
            'event_type': self.event_type,
            'reason': self.reason,
            'metadata': self.event_metadata or {},
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    @staticmethod
    def log_event(
        voice_id: Optional[int],
        event_type: str,
        user_id: Optional[int] = None,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "VoiceSlotEvent":
        """Persist a new slot event helper."""
        event = VoiceSlotEvent(
            voice_id=voice_id,
            user_id=user_id,
            event_type=event_type,
            reason=reason,
            event_metadata=metadata or {},
        )
        db.session.add(event)
        return event

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

            service_provider = VoiceModel._resolve_service_provider()
            voice_id = None

            # Create a voice record with pending status until asset persistence succeeds
            new_voice = Voice(
                name=voice_name,
                user_id=user_id,
                status=VoiceStatus.PENDING,
                allocation_status=VoiceAllocationStatus.RECORDED,
                service_provider=service_provider,
                elevenlabs_voice_id=None,
            )

            db.session.add(new_voice)
            db.session.flush()  # obtain primary key before uploading to S3
            voice_id = new_voice.id

            from utils.s3_client import S3Client

            file_extension = (filename.rsplit('.', 1)[1] if '.' in filename else 'wav').lower()
            recording_filesize = VoiceModel._determine_stream_size(file_data)
            try:
                file_data.seek(0)
            except (OSError, AttributeError):
                pass

            permanent_s3_key = (
                f"{VoiceModel.VOICE_SAMPLES_PREFIX}{user_id}/voice_{voice_id}_{uuid.uuid4()}.{file_extension}"
            )
            extra_args = {
                'ContentType': 'audio/mpeg' if file_extension == 'mp3' else 'audio/wav',
                'Metadata': {
                    'user_id': str(user_id),
                    'voice_id': str(voice_id),
                    'original_filename': filename,
                },
            }
            if Config.S3_REQUIRE_SSE:
                extra_args['ServerSideEncryption'] = 'AES256'

            upload_success = S3Client.upload_fileobj(file_data, permanent_s3_key, extra_args)
            if not upload_success:
                raise RuntimeError("Failed to upload voice sample to S3")

            logger.info("Stored voice recording at %s", permanent_s3_key)

            new_voice.recording_s3_key = permanent_s3_key
            new_voice.recording_filesize = recording_filesize
            new_voice.s3_sample_key = permanent_s3_key
            new_voice.sample_filename = filename
            new_voice.status = VoiceStatus.RECORDED
            new_voice.error_message = None

            VoiceSlotEvent.log_event(
                voice_id=voice_id,
                user_id=user_id,
                event_type=VoiceSlotEventType.RECORDING_UPLOADED,
                reason="initial_recording_uploaded",
                metadata={
                    's3_key': permanent_s3_key,
                    'filesize': recording_filesize,
                    'server_side_encryption': 'AES256' if Config.S3_REQUIRE_SSE else 'disabled',
                },
            )

            db.session.commit()

            # Queue async processing task for any additional hygiene/analysis
            from tasks.voice_tasks import process_voice_recording

            task = process_voice_recording.delay(
                voice_id=voice_id,
                s3_key=permanent_s3_key,
                filename=filename,
                user_id=user_id,
                voice_name=voice_name,
            )

            VoiceSlotEvent.log_event(
                voice_id=voice_id,
                user_id=user_id,
                event_type=VoiceSlotEventType.RECORDING_PROCESSING_QUEUED,
                reason="post_upload_processing",
                metadata={
                    'task_id': task.id,
                    's3_key': permanent_s3_key,
                },
            )
            db.session.commit()

            return True, {
                "id": voice_id,
                "name": voice_name,
                "status": VoiceStatus.RECORDED,
                "allocation_status": VoiceAllocationStatus.RECORDED,
                "task_id": task.id,
            }

        except Exception as e:
            logger.error("Exception in clone_voice: %s", str(e))

            if 'voice_id' in locals() and voice_id:
                try:
                    voice = Voice.query.get(voice_id)
                    if voice:
                        voice.status = VoiceStatus.ERROR
                        voice.allocation_status = VoiceAllocationStatus.RECORDED
                        voice.error_message = str(e)
                        VoiceSlotEvent.log_event(
                            voice_id=voice.id,
                            user_id=user_id,
                            event_type=VoiceSlotEventType.RECORDING_PROCESSING_FAILED,
                            reason="clone_voice_exception",
                            metadata={'error': str(e)},
                        )
                        db.session.commit()
                except Exception:
                    pass

            return False, str(e)
    
    @staticmethod
    def _clone_voice_api(
        file_data,
        filename,
        user_id,
        voice_name=None,
        remove_background_noise=False,
        service_provider=None,
    ):
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
            # Honor explicit provider to keep queue/provider decisions consistent
            provider = service_provider or VoiceModel._resolve_service_provider()
            
            # For ElevenLabs, we need to split the audio
            if provider == VoiceServiceProvider.ELEVENLABS:
                # Split audio into chunks if needed
                audio_chunks = split_audio_file(file_data, filename)
                logger.info(f"Split audio into {len(audio_chunks)} chunks")
                
                # Use the ElevenLabsService through VoiceService
                return VoiceService.clone_voice(
                    file_data=file_data,
                    filename=filename,
                    user_id=user_id,
                    voice_name=voice_name,
                    service=provider
                )
            else:
                # Use the CartesiaService through VoiceService
                return VoiceService.clone_voice(
                    file_data=file_data,
                    filename=filename,
                    user_id=user_id,
                    voice_name=voice_name,
                    language=language,
                    service=provider
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
            voice = VoiceModel.get_voice_by_id(voice_id)
            
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
                    external_voice_id=external_voice_id,
                    service=voice.service_provider
                )
            
            # Delete any S3 samples
            s3_success = True
            s3_message = "Voice sample deleted from S3"
            
            keys_to_delete = {key for key in [voice.s3_sample_key, voice.recording_s3_key] if key}
            if keys_to_delete:
                try:
                    from utils.s3_client import S3Client
                    S3Client.delete_objects(list(keys_to_delete))
                except Exception as e:
                    s3_success = False
                    s3_message = str(e)
                    logger.error(f"Exception deleting S3 sample: {str(e)}")
            
            # Log eviction event before deletion
            VoiceSlotEvent.log_event(
                voice_id=voice.id,
                user_id=voice.user_id,
                event_type=VoiceSlotEventType.SLOT_EVICTED,
                reason="manual_voice_delete",
                metadata={
                    'voice_id': voice_id,
                    'had_external_id': bool(external_voice_id),
                }
            )
            
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
    def get_voice_by_identifier(voice_identifier):
        """
        Resolve a voice using any supported identifier.

        Supports current external IDs (e.g., ElevenLabs), internal numeric IDs,
        and historical external IDs recorded before a slot eviction.
        """
        if not voice_identifier:
            return None

        # First try a live external identifier match.
        voice = VoiceModel.get_voice_by_elevenlabs_id(voice_identifier)
        if voice:
            return voice

        # Next attempt to interpret the identifier as an internal numeric ID.
        try:
            numeric_id = int(voice_identifier)
        except (TypeError, ValueError):
            numeric_id = None

        if numeric_id is not None:
            voice = VoiceModel.get_voice_by_id(numeric_id)
            if voice:
                return voice

        # Finally, fall back to historical allocation events so that mobile
        # clients holding an evicted external ID can still resolve the voice.
        voice_id = VoiceModel._get_voice_id_from_allocation_history(voice_identifier)
        if voice_id is not None:
            return VoiceModel.get_voice_by_id(voice_id)

        return None

    @staticmethod
    def _get_voice_id_from_allocation_history(external_voice_id: str):
        """Look up a voice ID using historical allocation events."""
        if not external_voice_id:
            return None

        try:
            event = (
                VoiceSlotEvent.query.filter(
                    VoiceSlotEvent.event_type == VoiceSlotEventType.ALLOCATION_COMPLETED,
                    VoiceSlotEvent.event_metadata["external_voice_id"].as_string() == external_voice_id,
                )
                .order_by(VoiceSlotEvent.created_at.desc())
                .first()
            )
        except Exception as exc:
            logger.debug(
                "Failed to inspect allocation history for external voice %s: %s",
                external_voice_id,
                exc,
            )
            return None

        return event.voice_id if event and event.voice_id else None
    
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
            if not voice:
                return False, "Voice sample not found"

            object_key = voice.s3_sample_key or voice.recording_s3_key
            if not object_key:
                return False, "Voice sample not found"

            # Allow recorded or ready voices to surface their sample
            if voice.status not in {VoiceStatus.RECORDED, VoiceStatus.READY}:
                return False, f"Voice is not ready (status: {voice.status})"

            url = S3Client.generate_presigned_url(
                object_key,
                expires_in,
                {'ResponseContentType': 'audio/mpeg'}
            )
            
            return True, url
        except Exception as e:
            logger.error(f"Exception getting sample URL: {str(e)}")
            return False, str(e)

    @staticmethod
    def _determine_stream_size(file_data) -> Optional[int]:
        """Best-effort helper to determine the size of an uploaded audio stream."""
        size: Optional[int] = None
        original_position: Optional[int] = None
        try:
            original_position = file_data.tell()
        except (AttributeError, OSError):
            original_position = None

        try:
            file_data.seek(0, os.SEEK_END)
            size = file_data.tell()
        except (AttributeError, OSError):
            size = None
        finally:
            try:
                if original_position is not None:
                    file_data.seek(original_position)
                else:
                    file_data.seek(0)
            except (AttributeError, OSError):
                pass

        return size

    @staticmethod
    def _resolve_service_provider() -> str:
        """Normalize configured service provider into a known constant."""
        provider = getattr(Config, 'PREFERRED_VOICE_SERVICE', VoiceServiceProvider.ELEVENLABS)
        if not provider:
            return VoiceServiceProvider.ELEVENLABS

        normalized = str(provider).strip().lower()
        if normalized in (VoiceServiceProvider.ELEVENLABS, VoiceServiceProvider.CARTESIA):
            return normalized

        logger.warning("Unknown voice service provider '%s'; defaulting to ElevenLabs.", provider)
        return VoiceServiceProvider.ELEVENLABS

    @staticmethod
    def list_active_allocations(limit: Optional[int] = 100) -> list:
        """List voices currently allocating or holding active slots."""
        query = Voice.query.filter(
            Voice.allocation_status.in_(
                [VoiceAllocationStatus.ALLOCATING, VoiceAllocationStatus.READY]
            )
        ).order_by(Voice.updated_at.desc())
        if limit and limit > 0:
            query = query.limit(limit)
        voices = query.all()
        return [voice.to_dict() for voice in voices]

    @staticmethod
    def recent_slot_events(limit: Optional[int] = 50) -> list:
        """Return the most recent slot events for observability."""
        query = VoiceSlotEvent.query.order_by(VoiceSlotEvent.created_at.desc())
        if limit and limit > 0:
            query = query.limit(limit)
        events = query.all()
        return [event.to_dict() for event in events]

    @staticmethod
    def count_ready_slots(service_provider: Optional[str] = None) -> int:
        """Count voices holding or acquiring remote slots (READY + ALLOCATING).

        Includes ALLOCATING voices to prevent over-subscription when
        multiple allocations are in flight concurrently.
        """
        query = Voice.query.filter(
            Voice.allocation_status.in_([
                VoiceAllocationStatus.READY,
                VoiceAllocationStatus.ALLOCATING,
            ])
        )
        if service_provider:
            query = query.filter(Voice.service_provider == service_provider)
        return query.count()

    @staticmethod
    def count_active_slots(service_provider: Optional[str] = None) -> int:
        """Count voices holding or acquiring remote slots (READY + ALLOCATING)."""
        query = Voice.query.filter(
            Voice.allocation_status.in_([
                VoiceAllocationStatus.READY,
                VoiceAllocationStatus.ALLOCATING,
            ])
        )
        if service_provider:
            query = query.filter(Voice.service_provider == service_provider)
        return query.count()

    @staticmethod
    def available_slot_capacity(service_provider: Optional[str] = None):
        """Return remaining slot capacity for the given provider.

        Counts both READY and ALLOCATING voices against the limit to prevent
        over-subscription when multiple allocations are in flight.
        """
        if service_provider and service_provider != VoiceServiceProvider.ELEVENLABS:
            # No enforced cap for non-ElevenLabs providers unless configured separately
            provider_limit = getattr(Config, "CARTESIA_SLOT_LIMIT", None)
            if provider_limit is None or provider_limit <= 0:
                return float("inf")
            used = VoiceModel.count_active_slots(service_provider)
            return max(0, provider_limit - used)

        limit = getattr(Config, "ELEVENLABS_SLOT_LIMIT", 0) or 0
        if limit <= 0:
            return float("inf")
        used = VoiceModel.count_active_slots(VoiceServiceProvider.ELEVENLABS)
        return max(0, limit - used)
