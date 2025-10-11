from pathlib import Path
from datetime import datetime
from config import Config
from database import db
from utils.credits import calculate_required_credits

# Database Model
class Story(db.Model):
    """Database model for stories"""
    __tablename__ = 'stories'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    author = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    content = db.Column(db.Text, nullable=False)
    cover_filename = db.Column(db.String(255), nullable=True)
    s3_cover_key = db.Column(db.String(512), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<Story {self.id}: {self.title}>"
    
    def to_dict(self):
        """Convert story to dictionary"""
        return {
            'id': self.id,
            'title': self.title,
            'author': self.author,
            'description': self.description,
            'content': self.content,
            'required_credits': calculate_required_credits(self.content),
            'cover_path': f'/stories/{self.id}/cover',
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


# Data Access Layer
class StoryModel:
    """Model for story data operations"""
    
    @staticmethod
    def get_all_stories():
        """
        Get all available stories
        
        Returns:
            list: List of story dictionaries
        """
        try:
            stories = Story.query.all()
            return [story.to_dict() for story in stories]
        except Exception as e:
            raise Exception(f"Error loading stories: {str(e)}")
    
    @staticmethod
    def get_story_by_id(story_id):
        """
        Get a specific story by ID
        
        Args:
            story_id: ID of the story to retrieve
            
        Returns:
            dict: Story data or None if not found
        """
        try:
            story = Story.query.get(story_id)
            
            if not story:
                return None
                
            return story.to_dict()
                
        except Exception as e:
            raise Exception(f"Error loading story {story_id}: {str(e)}")
    
    @staticmethod
    def get_story_cover_path(story_id):
        """
        Get the file path for a story's cover image
        
        Args:
            story_id: ID of the story
            
        Returns:
            Path: Path object for the story cover
        """
        story = Story.query.get(story_id)
        if story and story.cover_filename:
            return Config.STORIES_DIR / story.cover_filename
        return Config.STORIES_DIR / f"cover{story_id}.png"  # Fallback to old pattern
    
    @staticmethod
    def get_story_cover_s3_key(story_id):
        """
        Get the S3 key for a story's cover image
        
        Args:
            story_id: ID of the story
            
        Returns:
            str: S3 key for the cover image or None if not found
        """
        story = Story.query.get(story_id)
        if story and story.s3_cover_key:
            return story.s3_cover_key
        return None
    
    @staticmethod
    def generate_cover_presigned_url(story_id, expires_in=3600):
        """
        Generate a presigned URL for the story cover
        
        Args:
            story_id: ID of the story
            expires_in: URL expiration time in seconds (default: 1 hour)
            
        Returns:
            tuple: (success, url/error message)
        """
        try:
            s3_key = StoryModel.get_story_cover_s3_key(story_id)
            
            if not s3_key:
                return False, "Cover image not found in S3"
            
            # Get content type for response headers
            content_type = StoryModel._get_content_type_from_key(s3_key)
            
            # Use S3Client utility directly
            from utils.s3_client import S3Client
            
            presigned_url = S3Client.generate_presigned_url(
                s3_key,
                expires_in,
                {'ResponseContentType': content_type}
            )
            
            return True, presigned_url
            
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def _get_content_type_from_key(s3_key):
        """
        Determine the content type based on file extension in S3 key
        
        Args:
            s3_key: S3 object key
            
        Returns:
            str: Content type
        """
        import mimetypes
        import os
        
        # Get file extension from S3 key
        file_ext = os.path.splitext(s3_key)[1].lower()
        content_type = mimetypes.guess_type(s3_key)[0]
        
        # Default to appropriate image type if not detected
        if not content_type:
            if file_ext == '.jpg' or file_ext == '.jpeg':
                content_type = 'image/jpeg'
            elif file_ext == '.png':
                content_type = 'image/png'
            elif file_ext == '.gif':
                content_type = 'image/gif'
            elif file_ext == '.webp':
                content_type = 'image/webp'
            elif file_ext == '.svg':
                content_type = 'image/svg+xml'
            else:
                content_type = 'application/octet-stream'
                
        return content_type
