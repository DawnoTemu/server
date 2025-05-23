from models.story_model import StoryModel
from pathlib import Path

class StoryController:
    """Controller for story-related operations"""
    
    @staticmethod
    def get_all_stories():
        """
        Get list of all stories
        
        Returns:
            tuple: (success, data/error message, status_code)
        """
        try:
            stories = StoryModel.get_all_stories()
            return True, stories, 200
        except Exception as e:
            return False, {"error": str(e)}, 500
    
    @staticmethod
    def get_story(story_id):
        """
        Get a specific story by ID
        
        Args:
            story_id: ID of the story to retrieve
            
        Returns:
            tuple: (success, data/error message, status_code)
        """
        try:
            story = StoryModel.get_story_by_id(story_id)
            
            if story is None:
                return False, {"error": "Story not found"}, 404
                
            return True, story, 200
            
        except Exception as e:
            return False, {"error": str(e)}, 500
    
    @staticmethod
    def get_story_path(story_id):
        """
        Get file path for a story
        
        Args:
            story_id: ID of the story
            
        Returns:
            Path or None: Path object if story exists, None otherwise
        """
        path = StoryModel.get_story_path(story_id)
        return path if path.exists() else None
    
    @staticmethod
    def get_story_cover_path(story_id):
        """
        Get file path for a story's cover image (local file)
        
        Args:
            story_id: ID of the story
            
        Returns:
            Path or None: Path object if cover exists, None otherwise
        """
        path = StoryModel.get_story_cover_path(story_id)
        return path if path.exists() else None
    
    @staticmethod
    def get_story_cover_presigned_url(story_id, expires_in=3600):
        """
        Get presigned URL for a story's cover image from S3
        
        Args:
            story_id: ID of the story
            expires_in: URL expiration time in seconds
            
        Returns:
            tuple: (success, url/error message)
        """
        return StoryModel.generate_cover_presigned_url(story_id, expires_in)