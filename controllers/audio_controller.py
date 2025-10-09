from models.audio_model import AudioModel, AudioStatus, AudioStory
from models.story_model import StoryModel
from models.voice_model import VoiceModel, Voice, VoiceStatus
from models.credit_model import debit as credit_debit, refund_by_audio, InsufficientCreditsError
from utils.credits import calculate_required_credits
from database import db
import logging

# Configure logger
logger = logging.getLogger('audio_controller')

class AudioController:
    """Controller for audio-related operations"""
    
    @staticmethod
    def check_audio_exists(elevenlabs_voice_id, story_id):
        """
        Check if audio exists for a voice and story
        
        Args:
            elevenlabs_voice_id: ElevenLabs voice ID
            story_id: Story ID
            
        Returns:
            tuple: (success, data, status_code)
        """
        try:
            # Look up the voice by ElevenLabs ID to get the database ID
            voice = VoiceModel.get_voice_by_elevenlabs_id(elevenlabs_voice_id)
            
            if not voice:
                return False, {"error": "Voice not found"}, 404
            
            # Now check if audio exists using the database voice ID
            exists = AudioModel.check_audio_exists(voice.id, story_id)
            return True, {"exists": exists}, 200
        except Exception as e:
            logger.error(f"Error checking if audio exists: {str(e)}")
            return False, {"error": str(e)}, 500
    
    @staticmethod
    def get_audio(elevenlabs_voice_id, story_id, range_header=None):
        """
        Get audio data for a voice and story
        
        Args:
            elevenlabs_voice_id: ElevenLabs voice ID
            story_id: Story ID
            range_header: Optional HTTP Range header
            
        Returns:
            tuple: (success, audio_data/error message, status_code, extra_info)
        """
        try:
            # Look up the voice by ElevenLabs ID to get the database ID
            voice = VoiceModel.get_voice_by_elevenlabs_id(elevenlabs_voice_id)
            
            if not voice:
                return False, {"error": "Voice not found"}, 404, None
            
            # Get audio using the database voice ID
            success, data, extra = AudioModel.get_audio(voice.id, story_id, range_header)
            
            if not success:
                return False, {"error": str(data)}, 404, None
                
            # Status code is 206 for partial content (if range header was provided)
            status_code = 206 if range_header else 200
            
            return True, data, status_code, extra
        except Exception as e:
            logger.error(f"Error retrieving audio: {str(e)}")
            return False, {"error": f"Failed to retrieve audio: {str(e)}"}, 500, None
    
    @staticmethod
    def get_audio_presigned_url(elevenlabs_voice_id, story_id, expires_in=3600):
        """
        Get a presigned URL for direct S3 access
        
        Args:
            elevenlabs_voice_id: ElevenLabs voice ID
            story_id: Story ID
            expires_in: URL expiration time in seconds (default: 1 hour)
            
        Returns:
            tuple: (success, url/error message, status_code)
        """
        try:
            # Look up the voice by ElevenLabs ID to get the database ID
            voice = VoiceModel.get_voice_by_elevenlabs_id(elevenlabs_voice_id)
            
            if not voice:
                return False, "Voice not found", 404
            
            # First check if audio exists
            success, result, status = AudioController.check_audio_exists(elevenlabs_voice_id, story_id)
            
            if not success or not result.get('exists', False):
                return False, "Audio not found", 404
                
            # Generate presigned URL using database voice ID
            success, result = AudioModel.get_audio_presigned_url(voice.id, story_id, expires_in)
            
            if not success:
                return False, {"error": f"Failed to generate presigned URL: {result}"}, 500
                
            return True, result, 200
        except Exception as e:
            logger.error(f"Error generating audio URL: {str(e)}")
            return False, {"error": f"Failed to generate audio URL: {str(e)}"}, 500

    @staticmethod
    def synthesize_audio(elevenlabs_voice_id, story_id):
        """
        Synthesize audio for a story with a given voice
        
        Args:
            elevenlabs_voice_id: ElevenLabs voice ID
            story_id: Story ID
            
        Returns:
            tuple: (success, data/error message, status_code)
        """
        try:
            # Look up the voice by ElevenLabs ID to get the database ID
            voice = VoiceModel.get_voice_by_elevenlabs_id(elevenlabs_voice_id)
            
            if not voice:
                return False, {"error": "Voice not found"}, 404
            
            # Check if voice is ready    
            if voice.status != VoiceStatus.READY:
                return False, {
                    "error": f"Voice is not ready (status: {voice.status})",
                    "status": voice.status
                }, 400
                
            user_id = voice.user_id
                
            # Get story text
            story = StoryModel.get_story_by_id(story_id)
            
            if not story:
                return False, {"error": "Story not found"}, 404
                
            text = story.get("content")
            
            if not text:
                return False, {"error": "Story text not found in story"}, 400
                
            # Calculate required credits for this text
            required = calculate_required_credits(text)

            # Find or create audio record to inspect current status
            audio_record = AudioModel.find_or_create_audio_record(story_id, voice.id, user_id)

            # If already ready, return URL and do not charge
            if audio_record.status == AudioStatus.READY.value and audio_record.s3_key:
                success, url = AudioModel.get_audio_presigned_url(voice.id, story_id)
                if success:
                    return True, {"status": "ready", "url": url, "id": audio_record.id}, 200
                return False, {"error": "Failed to generate URL"}, 500

            # If processing, don't double-charge
            if audio_record.status == AudioStatus.PROCESSING.value:
                return True, {
                    "status": "processing",
                    "id": audio_record.id,
                    "message": "Audio synthesis is already in progress"
                }, 202

            # Prepare record for new processing attempt and attempt to charge
            audio_record.status = AudioStatus.PENDING.value
            audio_record.error_message = None
            audio_record.credits_charged = required
            try:
                # Debit will also commit the session; pending changes will be included
                _, debit_tx, charged_delta = credit_debit(
                    user_id=user_id,
                    amount=required,
                    reason=f"audio_synthesis:{story_id}",
                    audio_story_id=audio_record.id,
                    story_id=story_id,
                )
            except InsufficientCreditsError as e:
                # Roll back and return 402 Payment Required
                db.session.rollback()
                return False, {"error": str(e), "required": required}, 402
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error debiting credits: {e}")
                return False, {"error": "Failed to charge credits"}, 500

            # Queue async task; if queueing fails, refund credits and mark error
            try:
                from tasks.audio_tasks import synthesize_audio_task
                task = synthesize_audio_task.delay(audio_record.id, voice.id, story_id, text)
                logger.info(f"Queued audio synthesis task {task.id} for audio ID {audio_record.id}")
            except Exception as qe:
                logger.error(f"Queueing synthesis task failed: {qe}")
                # Refund only if this call actually charged any delta
                if 'charged_delta' in locals() and charged_delta and charged_delta > 0:
                    try:
                        refund_by_audio(audio_record.id, reason="queue_failed")
                    except Exception as re:
                        logger.error(f"Refund after queue failure also failed: {re}")
                # Mark record as error to unblock future attempts
                try:
                    audio_record.status = AudioStatus.ERROR.value
                    audio_record.error_message = "Queueing failed"
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                return False, {"error": "Failed to queue synthesis task"}, 503

            return True, {
                "status": "pending",
                "id": audio_record.id,
                "message": "Audio synthesis has been queued"
            }, 202
            
        except Exception as e:
            logger.error(f"Error synthesizing audio: {str(e)}")
            return False, {"error": str(e)}, 500
