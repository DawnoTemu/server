import os
import sys
import pytest
import json
from io import BytesIO
from unittest.mock import MagicMock, patch
from pathlib import Path

# Add the application root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import Config
from app import app as flask_app


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up test environment variables and directories"""
    # Set environment variables for testing
    os.environ["ELEVENLABS_API_KEY"] = "test_api_key"
    os.environ["AWS_ACCESS_KEY_ID"] = "test_aws_key"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "test_aws_secret"
    os.environ["AWS_REGION"] = "test-region-1"
    os.environ["S3_BUCKET_NAME"] = "test-bucket"
    
    # Create test directories
    Path("uploads").mkdir(exist_ok=True)
    Path("stories").mkdir(exist_ok=True)
    Path("tests/fixtures").mkdir(exist_ok=True, parents=True)
    
    yield
    
    # Cleanup (if needed)
    # Note: We're not removing directories since they may be used by other tests


@pytest.fixture
def app():
    """Flask application fixture"""
    with patch('config.Config.validate', return_value=True):  # Force validation to pass
        yield flask_app


@pytest.fixture
def client(app):
    """Flask test client fixture"""
    with app.test_client() as test_client:
        with app.app_context():
            yield test_client


@pytest.fixture
def mock_s3_client():
    """Mock boto3 S3 client"""
    mock_client = MagicMock()
    
    # Configure the mock client methods with default behaviors
    mock_client.head_object.return_value = {}
    mock_client.get_object.return_value = {
        'Body': BytesIO(b'mock audio data'),
        'ContentLength': 1000,
        'ContentRange': 'bytes 0-999/1000'
    }
    mock_client.upload_fileobj.return_value = None
    mock_client.generate_presigned_url.return_value = "https://example.com/presigned-url"
    
    # Configure paginator
    mock_paginator = MagicMock()
    mock_page = {'Contents': [{'Key': 'voice-id/1.mp3'}, {'Key': 'voice-id/2.mp3'}]}
    mock_paginator.paginate.return_value = [mock_page]
    mock_client.get_paginator.return_value = mock_paginator
    
    # Configure delete_objects
    mock_client.delete_objects.return_value = {}
    
    with patch('config.Config.get_s3_client', return_value=mock_client):
        yield mock_client


@pytest.fixture
def sample_audio_file():
    """Generate a sample audio file for testing"""
    return BytesIO(b'mock wav audio data')


@pytest.fixture
def sample_stories_directory():
    """Create sample story files for testing"""
    stories_dir = Path("stories")
    
    # Create test story files
    for i in range(1, 3):
        story_data = {
            "id": i,
            "title": f"Test Story {i}",
            "author": "Test Author",
            "description": f"Description for Test Story {i}",
            "content": f"Content for Test Story {i}"
        }
        
        with open(stories_dir / f"{i}.json", 'w') as f:
            json.dump(story_data, f)
    
    yield stories_dir
    
    # Clean up test story files
    for i in range(1, 3):
        story_file = stories_dir / f"{i}.json"
        if story_file.exists():
            story_file.unlink()


@pytest.fixture
def mock_elevenlabs_session():
    """Mock requests session for ElevenLabs API"""
    # Create a proper mock with the headers attribute as a dictionary
    mock_session = MagicMock()
    mock_session.headers = {}  # Initialize as dict, not a mock
    
    # Configure post method to return successful response for voice cloning
    mock_post_response = MagicMock()
    mock_post_response.status_code = 200
    mock_post_response.json.return_value = {
        "voice_id": "test-voice-id-123",
        "name": "Test Voice"
    }
    mock_post_response.content = b'mock audio content'
    mock_post_response.raise_for_status.return_value = None
    mock_session.post.return_value = mock_post_response
    
    # Configure delete method for voice deletion
    mock_delete_response = MagicMock()
    mock_delete_response.status_code = 200
    mock_delete_response.json.return_value = {"status": "success"}
    mock_session.delete.return_value = mock_delete_response
    
    # Patch the function that creates the session
    with patch('requests.Session', return_value=mock_session):
        yield mock_session