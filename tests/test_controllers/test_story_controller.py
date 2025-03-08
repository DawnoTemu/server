import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from controllers.story_controller import StoryController


class TestStoryController:
    """Tests for the StoryController class"""
    
    @patch('models.story_model.StoryModel.get_all_stories')
    def test_get_all_stories_success(self, mock_get_all):
        """Test successfully retrieving all stories"""
        # Arrange
        mock_stories = [
            {"id": 1, "title": "Story 1"},
            {"id": 2, "title": "Story 2"}
        ]
        mock_get_all.return_value = mock_stories
        
        # Act
        success, data, status_code = StoryController.get_all_stories()
        
        # Assert
        assert success is True
        assert data == mock_stories
        assert status_code == 200
        mock_get_all.assert_called_once()

    @patch('models.story_model.StoryModel.get_all_stories')
    def test_get_all_stories_error(self, mock_get_all):
        """Test error handling when retrieving all stories"""
        # Arrange
        mock_get_all.side_effect = Exception("Database error")
        
        # Act
        success, data, status_code = StoryController.get_all_stories()
        
        # Assert
        assert success is False
        assert "error" in data
        assert "Database error" in data["error"]
        assert status_code == 500

    @patch('models.story_model.StoryModel.get_story_by_id')
    def test_get_story_exists(self, mock_get_story):
        """Test retrieving a story that exists"""
        # Arrange
        story_id = 1
        mock_story = {"id": 1, "title": "Test Story"}
        mock_get_story.return_value = mock_story
        
        # Act
        success, data, status_code = StoryController.get_story(story_id)
        
        # Assert
        assert success is True
        assert data == mock_story
        assert status_code == 200
        mock_get_story.assert_called_once_with(story_id)

    @patch('models.story_model.StoryModel.get_story_by_id')
    def test_get_story_not_found(self, mock_get_story):
        """Test retrieving a story that doesn't exist"""
        # Arrange
        story_id = 999
        mock_get_story.return_value = None
        
        # Act
        success, data, status_code = StoryController.get_story(story_id)
        
        # Assert
        assert success is False
        assert "error" in data
        assert "Story not found" in data["error"]
        assert status_code == 404

    @patch('models.story_model.StoryModel.get_story_by_id')
    def test_get_story_error(self, mock_get_story):
        """Test error handling when retrieving a specific story"""
        # Arrange
        story_id = 1
        mock_get_story.side_effect = Exception("Database error")
        
        # Act
        success, data, status_code = StoryController.get_story(story_id)
        
        # Assert
        assert success is False
        assert "error" in data
        assert "Database error" in data["error"]
        assert status_code == 500

    @patch('models.story_model.StoryModel.get_story_path')
    @patch('pathlib.Path.exists')
    def test_get_story_path_exists(self, mock_exists, mock_get_path):
        """Test getting the file path for a story that exists"""
        # Arrange
        story_id = 1
        mock_path = Path("stories/1.json")
        mock_get_path.return_value = mock_path
        mock_exists.return_value = True
        
        # Act
        path = StoryController.get_story_path(story_id)
        
        # Assert
        assert path == mock_path
        mock_get_path.assert_called_once_with(story_id)

    @patch('models.story_model.StoryModel.get_story_path')
    @patch('pathlib.Path.exists')
    def test_get_story_path_not_exists(self, mock_exists, mock_get_path):
        """Test getting the file path for a story that doesn't exist"""
        # Arrange
        story_id = 999
        mock_path = Path("stories/999.json")
        mock_get_path.return_value = mock_path
        mock_exists.return_value = False
        
        # Act
        path = StoryController.get_story_path(story_id)
        
        # Assert
        assert path is None
        mock_get_path.assert_called_once_with(story_id)

    @patch('models.story_model.StoryModel.get_story_cover_path')
    @patch('pathlib.Path.exists')
    def test_get_story_cover_path_exists(self, mock_exists, mock_get_path):
        """Test getting the file path for a story cover that exists"""
        # Arrange
        story_id = 1
        mock_path = Path("stories/cover1.png")
        mock_get_path.return_value = mock_path
        mock_exists.return_value = True
        
        # Act
        path = StoryController.get_story_cover_path(story_id)
        
        # Assert
        assert path == mock_path
        mock_get_path.assert_called_once_with(story_id)

    @patch('models.story_model.StoryModel.get_story_cover_path')
    @patch('pathlib.Path.exists')
    def test_get_story_cover_path_not_exists(self, mock_exists, mock_get_path):
        """Test getting the file path for a story cover that doesn't exist"""
        # Arrange
        story_id = 999
        mock_path = Path("stories/cover999.png")
        mock_get_path.return_value = mock_path
        mock_exists.return_value = False
        
        # Act
        path = StoryController.get_story_cover_path(story_id)
        
        # Assert
        assert path is None
        mock_get_path.assert_called_once_with(story_id)