import json
from config import Config
from pathlib import Path

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
            stories = []
            for file in Config.STORIES_DIR.glob('*.json'):
                if file.name == 'index.json':
                    continue
                    
                with open(file, 'r', encoding='utf-8') as f:
                    story_data = json.load(f)
                    story_id = story_data.get('id')
                    stories.append({
                        'id': story_id,
                        'title': story_data.get('title'),
                        'author': story_data.get('author'),
                        'description': story_data.get('description'),
                        'content': story_data.get('content'),
                        'cover_path':  '/api/stories/' + str(story_id) + '/cover.png'
                    })
            return stories
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
            story_path = Config.STORIES_DIR / f"{story_id}.json"
            
            if not story_path.exists():
                return None
                
            with open(story_path, 'r', encoding='utf-8') as f:
                return json.load(f)
                
        except Exception as e:
            raise Exception(f"Error loading story {story_id}: {str(e)}")
    
    @staticmethod
    def get_story_path(story_id):
        """
        Get the file path for a story
        
        Args:
            story_id: ID of the story
            
        Returns:
            Path: Path object for the story
        """
        return Config.STORIES_DIR / f"{story_id}.json"
    
    @staticmethod
    def get_story_cover_path(story_id):
        """
        Get the file path for a story's cover image
        
        Args:
            story_id: ID of the story
            
        Returns:
            Path: Path object for the story cover
        """
        return Config.STORIES_DIR / f"cover{story_id}.png"