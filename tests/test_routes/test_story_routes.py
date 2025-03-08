import pytest
import json
from unittest.mock import patch, MagicMock
from pathlib import Path
from flask import jsonify


class TestStoryRoutes:
    """Tests for the story routes"""
    
    @patch('controllers.story_controller.StoryController.get_all_stories')
    def test_list_stories_success(self, mock_get_all, client):
        """Test successfully listing all stories"""
        # Arrange
        mock_stories = [
            {"id": 1, "title": "Story 1"},
            {"id": 2, "title": "Story 2"}
        ]
        mock_get_all.return_value = (True, mock_stories, 200)
        
        # Act
        response = client.get('/api/stories')
        
        # Assert
        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data) == 2
        assert data[0]["title"] == "Story 1"
        assert data[1]["title"] == "Story 2"
        mock_get_all.assert_called_once()

    @patch('controllers.story_controller.StoryController.get_all_stories')
    def test_list_stories_error(self, mock_get_all, client):
        """Test error handling when listing stories"""
        # Arrange
        mock_get_all.return_value = (False, {"error": "Database error"}, 500)
        
        # Act
        response = client.get('/api/stories')
        
        # Assert
        assert response.status_code == 500
        data = json.loads(response.data)
        assert "error" in data
        assert "Database error" in data["error"]

    def test_get_story_success(self, client, sample_stories_directory):
        """Test successfully getting a specific story using sample files in test directory"""
        # Arrange
        story_id = 1
        
        # Act
        response = client.get(f'/api/stories/{story_id}')
        
        # Assert
        assert response.status_code < 400, f"Expected success status, got {response.status_code}"
        data = json.loads(response.data)
        assert data["id"] == story_id
        assert data["title"] == f"Test Story {story_id}"

    @patch('controllers.story_controller.StoryController.get_story_path')
    def test_get_story_not_found(self, mock_get_path, client):
        """Test getting a story that doesn't exist"""
        # Arrange
        story_id = 999
        mock_get_path.return_value = None
        
        # Act
        response = client.get(f'/api/stories/{story_id}')
        
        # Assert
        assert response.status_code == 404
        data = json.loads(response.data)
        assert "error" in data
        assert "Story not found" in data["error"]
        mock_get_path.assert_called_once_with(story_id)

    def test_get_story_cover_success(self, client, sample_stories_directory):
        """Test successfully getting a story cover image using actual sample files"""
        # Note: This will only work if your sample_stories_directory fixture also creates cover images
        # You may need to adapt this test based on your actual fixture implementation
        # Arrange
        story_id = 1
        
        # Create a mock cover image if it doesn't exist
        cover_path = sample_stories_directory / f"cover{story_id}.png"
        if not cover_path.exists():
            with open(cover_path, 'wb') as f:
                f.write(b'PNG MOCK DATA')
        
        # Act
        response = client.get(f'/api/stories/{story_id}/cover.png')
        
        # Assert
        assert response.status_code < 400, f"Expected success status, got {response.status_code}"

    @patch('controllers.story_controller.StoryController.get_story_cover_path')
    def test_get_story_cover_not_found(self, mock_get_path, client):
        """Test getting a story cover that doesn't exist"""
        # Arrange
        story_id = 999
        mock_get_path.return_value = None
        
        # Act
        response = client.get(f'/api/stories/{story_id}/cover.png')
        
        # Assert
        assert response.status_code == 404
        data = json.loads(response.data)
        assert "error" in data
        assert "Cover image not found" in data["error"]
        mock_get_path.assert_called_once_with(story_id)