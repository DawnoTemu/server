import json
from unittest.mock import patch


class TestStoryRoutes:
    """Tests for the story routes"""

    @patch('controllers.story_controller.StoryController.get_all_stories')
    def test_list_stories_success(self, mock_get_all, client):
        """Test successfully listing all stories"""
        mock_stories = [
            {"id": 1, "title": "Story 1", "required_credits": 3},
            {"id": 2, "title": "Story 2", "required_credits": 1}
        ]
        mock_get_all.return_value = (True, mock_stories, 200)

        response = client.get('/stories')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data) == 2
        assert data[0]["title"] == "Story 1"
        assert data[1]["title"] == "Story 2"
        assert data[0]["required_credits"] == 3
        assert data[1]["required_credits"] == 1
        mock_get_all.assert_called_once()

    @patch('controllers.story_controller.StoryController.get_all_stories')
    def test_list_stories_error(self, mock_get_all, client):
        """Test error handling when listing stories"""
        mock_get_all.return_value = (False, {"error": "Database error"}, 500)

        response = client.get('/stories')

        assert response.status_code == 500
        data = json.loads(response.data)
        assert "error" in data
        assert "Database error" in data["error"]

    @patch('controllers.story_controller.StoryController.get_story')
    def test_get_story_success(self, mock_get_story, client):
        """Test successfully getting a specific story"""
        mock_get_story.return_value = (True, {"id": 1, "title": "Test Story 1", "required_credits": 2}, 200)

        response = client.get('/stories/1')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["id"] == 1
        assert data["title"] == "Test Story 1"
        assert "required_credits" in data

    @patch('controllers.story_controller.StoryController.get_story')
    def test_get_story_not_found(self, mock_get_story, client):
        """Test getting a story that doesn't exist"""
        mock_get_story.return_value = (False, {"error": "Story not found"}, 404)

        response = client.get('/stories/999')

        assert response.status_code == 404
        data = json.loads(response.data)
        assert "error" in data
        assert "Story not found" in data["error"]

    @patch('controllers.story_controller.StoryController.get_story_cover_presigned_url')
    def test_get_story_cover_success(self, mock_get_cover, client):
        """Test successfully getting a story cover image redirect"""
        mock_get_cover.return_value = (True, "https://s3.example.com/cover1.png")

        response = client.get('/stories/1/cover')

        assert response.status_code == 302

    @patch('controllers.story_controller.StoryController.get_story_cover_presigned_url')
    def test_get_story_cover_not_found(self, mock_get_cover, client):
        """Test getting a story cover that doesn't exist"""
        mock_get_cover.return_value = (False, "Cover image not found")

        response = client.get('/stories/999/cover')

        assert response.status_code == 404
        data = json.loads(response.data)
        assert "error" in data
        assert "Cover image not found" in data["error"]
