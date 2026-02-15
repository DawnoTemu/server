import pytest
from unittest.mock import patch
from pathlib import Path

from models.story_model import StoryModel, Story
from database import db


class TestStoryModel:
    """Tests for the StoryModel class"""

    def test_get_all_stories(self, app):
        """Test retrieving all stories from the database"""
        with app.app_context():
            story = Story(
                title="Test Story 1",
                author="Test Author",
                description="A test story",
                content="Once upon a time in a land far away",
            )
            db.session.add(story)
            db.session.commit()

            stories = StoryModel.get_all_stories()

            assert len(stories) > 0
            assert "title" in stories[0]
            assert "author" in stories[0]
            assert "content" in stories[0]
            assert "required_credits" in stories[0]

    def test_get_all_stories_error(self, app):
        """Test error handling when loading stories fails"""
        with app.app_context():
            with patch('models.story_model.Story.query') as mock_query:
                mock_query.all.side_effect = Exception("Database error")
                with pytest.raises(Exception) as excinfo:
                    StoryModel.get_all_stories()
                assert "Error loading stories" in str(excinfo.value)

    def test_get_story_by_id_exists(self, app):
        """Test retrieving a story that exists"""
        with app.app_context():
            story = Story(
                title="Findable Story",
                author="Test Author",
                description="A findable story",
                content="Content of the findable story",
            )
            db.session.add(story)
            db.session.commit()
            story_id = story.id

            result = StoryModel.get_story_by_id(story_id)

            assert result is not None
            assert result["id"] == story_id
            assert result["title"] == "Findable Story"
            assert "required_credits" in result

    def test_get_story_by_id_not_exists(self, app):
        """Test retrieving a story that doesn't exist"""
        with app.app_context():
            story = StoryModel.get_story_by_id(99999)
            assert story is None

    def test_get_story_by_id_error(self, app):
        """Test error handling when loading a specific story fails"""
        with app.app_context():
            with patch('models.story_model.Story.query') as mock_query:
                mock_query.get.side_effect = Exception("Database error")
                with pytest.raises(Exception) as excinfo:
                    StoryModel.get_story_by_id(1)
                assert "Error loading story" in str(excinfo.value)

    def test_get_story_cover_path(self, app):
        """Test getting the file path for a story cover image"""
        with app.app_context():
            story = Story(
                title="Cover Story",
                author="Test Author",
                description="Story with cover",
                content="Content",
                cover_filename="custom_cover.png",
            )
            db.session.add(story)
            db.session.commit()

            path = StoryModel.get_story_cover_path(story.id)
            assert isinstance(path, Path)
            assert path.name == "custom_cover.png"

    def test_get_story_cover_path_fallback(self, app):
        """Test cover path falls back to default pattern when no cover_filename"""
        with app.app_context():
            story = Story(
                title="No Cover Story",
                author="Test Author",
                description="Story without cover",
                content="Content",
            )
            db.session.add(story)
            db.session.commit()

            path = StoryModel.get_story_cover_path(story.id)
            assert isinstance(path, Path)
            assert path.name == f"cover{story.id}.png"
