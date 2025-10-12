from datetime import datetime
from typing import Tuple, Dict, Any
import json
import logging
import os
import tempfile
from pathlib import Path

import requests

from database import db
from models.story_model import Story
from models.voice_model import VoiceModel, VoiceAllocationStatus
from utils.s3_client import S3Client
from utils.voice_slot_queue import VoiceSlotQueue

logger = logging.getLogger("admin_controller")

class AdminController:
    """Controller for administrative operations"""
    
    @staticmethod
    def upload_story(story_data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], int]:
        """
        Upload a story to the database with duplicate checking
        
        Args:
            story_data: Dictionary containing story information
            
        Returns:
            Tuple[bool, Dict[str, Any], int]: (success, result, status_code)
        """
        try:
            # Validate required fields
            required_fields = ['title', 'author', 'content']
            missing_fields = [field for field in required_fields if not story_data.get(field)]
            
            if missing_fields:
                return False, {
                    "error": f"Missing required fields: {', '.join(missing_fields)}"
                }, 400
            
            # Check for duplicate by title and author
            existing_story = Story.query.filter_by(
                title=story_data['title'],
                author=story_data['author']
            ).first()
            
            if existing_story:
                return True, {
                    "message": "Story already exists",
                    "duplicate": True,
                    "existing_story_id": existing_story.id,
                    "story_id": existing_story.id
                }, 200
            
            # Create new story
            new_story = Story(
                title=story_data['title'],
                author=story_data['author'],
                description=story_data.get('description', ''),
                content=story_data['content'],
                cover_filename=story_data.get('cover_filename'),
                s3_cover_key=story_data.get('s3_cover_key'),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            db.session.add(new_story)
            db.session.commit()
            
            return True, {
                "message": "Story uploaded successfully",
                "duplicate": False,
                "story_id": new_story.id,
                "story": new_story.to_dict()
            }, 201
            
        except Exception as e:
            db.session.rollback()
            return False, {
                "error": f"Failed to upload story: {str(e)}"
            }, 500
    
    @staticmethod
    def bulk_upload_stories(stories_data: list) -> Tuple[bool, Dict[str, Any], int]:
        """
        Upload multiple stories with duplicate checking
        
        Args:
            stories_data: List of story dictionaries
            
        Returns:
            Tuple[bool, Dict[str, Any], int]: (success, result, status_code)
        """
        try:
            results = {
                'uploaded': [],
                'duplicates': [],
                'failed': [],
                'summary': {
                    'total': len(stories_data),
                    'uploaded_count': 0,
                    'duplicate_count': 0,
                    'failed_count': 0
                }
            }
            
            for story_data in stories_data:
                success, result, status_code = AdminController.upload_story(story_data)
                
                if success:
                    if result.get('duplicate'):
                        results['duplicates'].append({
                            'title': story_data['title'],
                            'existing_id': result['existing_story_id']
                        })
                        results['summary']['duplicate_count'] += 1
                    else:
                        results['uploaded'].append({
                            'title': story_data['title'],
                            'story_id': result['story_id']
                        })
                        results['summary']['uploaded_count'] += 1
                else:
                    results['failed'].append({
                        'title': story_data.get('title', 'Unknown'),
                        'error': result.get('error', 'Unknown error')
                    })
                    results['summary']['failed_count'] += 1
            
            return True, results, 200
            
        except Exception as e:
            return False, {
                "error": f"Bulk upload failed: {str(e)}"
            }, 500
    
    @staticmethod
    def upload_story_with_image(story_data: Dict[str, Any], image_url: str = None) -> Tuple[bool, Dict[str, Any], int]:
        """
        Upload a story with optional image upload to S3
        
        Args:
            story_data: Dictionary containing story information
            image_url: Optional URL to download cover image from
            
        Returns:
            Tuple[bool, Dict[str, Any], int]: (success, result, status_code)
        """
        try:
            # First upload the story
            success, result, status_code = AdminController.upload_story(story_data)
            
            if not success or result.get('duplicate'):
                return success, result, status_code
            
            story_id = result['story_id']
            
            # If image URL is provided, download and upload to S3
            if image_url:
                try:
                    image_success, s3_key = AdminController._upload_image_to_s3(image_url, story_id)
                    
                    if image_success:
                        # Update story with S3 key
                        story = Story.query.get(story_id)
                        if story:
                            story.s3_cover_key = s3_key
                            story.updated_at = datetime.utcnow()
                            db.session.commit()
                            
                            result['story']['s3_cover_key'] = s3_key
                            result['image_uploaded'] = True
                    else:
                        result['image_uploaded'] = False
                        result['image_error'] = s3_key  # s3_key contains error message on failure
                
                except Exception as e:
                    result['image_uploaded'] = False
                    result['image_error'] = str(e)
            
            return True, result, status_code
            
        except Exception as e:
            return False, {
                "error": f"Failed to upload story with image: {str(e)}"
            }, 500
    
    @staticmethod
    def get_voice_slot_status(
        limit_active: int = 100,
        limit_queue: int = 50,
        limit_events: int = 50,
    ) -> Tuple[bool, Dict[str, Any], int]:
        """Return snapshot of voice slot utilisation and recent activity."""
        try:
            from config import Config

            active_voices = VoiceModel.list_active_allocations(limit_active)
            queue_entries = VoiceSlotQueue.snapshot(limit_queue)
            recent_events = VoiceModel.recent_slot_events(limit_events)

            ready_count = sum(
                1 for voice in active_voices if voice.get("allocation_status") == VoiceAllocationStatus.READY
            )
            allocating_count = sum(
                1 for voice in active_voices if voice.get("allocation_status") == VoiceAllocationStatus.ALLOCATING
            )

            metrics = {
                "slot_limit": getattr(Config, "ELEVENLABS_SLOT_LIMIT", None),
                "available_capacity": VoiceModel.available_slot_capacity(),
                "ready_count": ready_count,
                "allocating_count": allocating_count,
                "queue_depth": VoiceSlotQueue.length(),
            }

            payload = {
                "metrics": metrics,
                "active_voices": active_voices,
                "queued_requests": queue_entries,
                "recent_events": recent_events,
            }
            return True, payload, 200
        except Exception as exc:
            logger.error("Failed to build voice slot status snapshot: %s", exc)
            return False, {"error": f"Failed to load voice slot status: {exc}"}, 500

    @staticmethod
    def trigger_voice_queue_processing() -> Tuple[bool, Dict[str, Any], int]:
        """Kick off background processing of queued voice allocation requests."""
        try:
            from tasks.voice_tasks import process_voice_queue

            task = process_voice_queue.delay()
            return True, {
                "message": "Voice allocation queue processing triggered",
                "task_id": getattr(task, "id", None),
            }, 202
        except Exception as exc:
            logger.error("Failed to trigger voice queue processing: %s", exc)
            return False, {"error": f"Failed to trigger queue processing: {exc}"}, 500
    
    @staticmethod
    def _upload_image_to_s3(image_url: str, story_id: int) -> Tuple[bool, str]:
        """
        Download image from URL and upload to S3
        
        Args:
            image_url: URL to download image from
            story_id: ID of the story
            
        Returns:
            Tuple[bool, str]: (success, s3_key_or_error_message)
        """
        try:
            # Download image
            response = requests.get(image_url, timeout=30)
            response.raise_for_status()
            
            # Determine file extension
            content_type = response.headers.get('content-type', '').lower()
            if 'jpeg' in content_type or 'jpg' in content_type:
                ext = '.jpg'
            elif 'png' in content_type:
                ext = '.png'
            elif 'gif' in content_type:
                ext = '.gif'
            elif 'webp' in content_type:
                ext = '.webp'
            else:
                ext = '.jpg'  # Default
            
            # Create temporary file
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as temp_file:
                temp_file.write(response.content)
                temp_path = temp_file.name
            
            try:
                # Upload to S3
                s3_key = f"stories/covers/story_{story_id}_cover{ext}"
                
                upload_success = S3Client.upload_file(
                    temp_path,
                    s3_key,
                    content_type=content_type
                )
                
                if upload_success:
                    return True, s3_key
                else:
                    return False, "Failed to upload to S3"
                    
            finally:
                # Clean up temporary file
                try:
                    os.unlink(temp_path)
                except:
                    pass
                    
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def get_stories_stats() -> Tuple[bool, Dict[str, Any], int]:
        """
        Get statistics about stories in the database
        
        Returns:
            Tuple[bool, Dict[str, Any], int]: (success, result, status_code)
        """
        try:
            total_stories = Story.query.count()
            stories_with_covers = Story.query.filter(
                (Story.cover_filename.isnot(None)) | (Story.s3_cover_key.isnot(None))
            ).count()
            stories_with_s3_covers = Story.query.filter(Story.s3_cover_key.isnot(None)).count()
            
            # Get authors list
            authors = db.session.query(Story.author).distinct().all()
            authors_list = [author[0] for author in authors]
            
            return True, {
                "total_stories": total_stories,
                "stories_with_covers": stories_with_covers,
                "stories_with_s3_covers": stories_with_s3_covers,
                "authors": authors_list,
                "authors_count": len(authors_list)
            }, 200
            
        except Exception as e:
            return False, {
                "error": f"Failed to get stories stats: {str(e)}"
            }, 500 
