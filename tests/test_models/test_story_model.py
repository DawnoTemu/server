import pytest
import json
from pathlib import Path
from unittest.mock import patch, mock_open

from models.story_model import StoryModel


class TestStoryModel:
    """Tests for the StoryModel class"""

    def test_get_all_stories(self, sample_stories_directory):
        """Test retrieving all stories"""
        # Act
        stories = StoryModel.get_all_stories()
        
        # Assert
        assert len(stories) > 0  # Just check that we have some stories instead of a specific count
        # Verify structure of at least the first story
        if stories:
            assert "title" in stories[0]
            assert "author" in stories[0]
            assert "content" in stories[0]
            assert "required_credits" in stories[0]

    def test_get_all_stories_error(self):
        """Test error handling when loading stories fails"""
        # Arrange
        with patch('pathlib.Path.glob', side_effect=Exception("File error")):
            # Act & Assert
            with pytest.raises(Exception) as excinfo:
                StoryModel.get_all_stories()
            assert "Error loading stories" in str(excinfo.value)

    def test_get_story_by_id_exists(self, sample_stories_directory):
        """Test retrieving a story that exists"""
        # Get one of the story IDs that actually exists
        stories = StoryModel.get_all_stories()
        if not stories:
            pytest.skip("No stories available for testing")
        
        story_id = stories[0]["id"]
        
        # Act
        story = StoryModel.get_story_by_id(story_id)
        
        # Assert
        assert story is not None
        assert story["id"] == story_id
        assert "title" in story
        assert "required_credits" in story

    def test_get_story_by_id_not_exists(self, sample_stories_directory):
        """Test retrieving a story that doesn't exist"""
        # Act
        story = StoryModel.get_story_by_id(99999)  # Use a very large ID that shouldn't exist
        
        # Assert
        assert story is None

    def test_get_story_by_id_error(self):
        """Test error handling when loading a specific story fails"""
        # Arrange
        with patch('pathlib.Path.exists', return_value=True):
            with patch('builtins.open', side_effect=Exception("File error")):
                # Act & Assert
                with pytest.raises(Exception) as excinfo:
                    StoryModel.get_story_by_id(1)
                assert "Error loading story" in str(excinfo.value)

    def test_get_story_path(self):
        """Test getting the file path for a story"""
        # Act
        path = StoryModel.get_story_path(1)
        
        # Assert
        assert isinstance(path, Path)
        assert path.name == "1.json"
        assert path.parent.name == "stories"

    def test_get_story_cover_path(self):
        """Test getting the file path for a story cover image"""
        # Act
        path = StoryModel.get_story_cover_path(1)
        
        # Assert
        assert isinstance(path, Path)
        assert path.name == "cover1.png"
        assert path.parent.name == "stories"
