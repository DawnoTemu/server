from pathlib import Path
from datetime import datetime
from config import Config
from database import db

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
            'cover_path': f'/api/stories/{self.id}/cover.png' if self.cover_filename else None,
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