import os
import sys
import pytest
import json
from io import BytesIO
from unittest.mock import MagicMock, patch
from pathlib import Path

# Add the application root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Exclude standalone integration scripts that use argparse / requests
collect_ignore = [
    os.path.join(os.path.dirname(__file__), "test_voice_quality_comparison.py"),
]

from config import Config
from database import db


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up test environment variables and directories"""
    # Set environment variables for testing
    os.environ["ELEVENLABS_API_KEY"] = "test_api_key"
    os.environ["CARTESIA_API_KEY"] = "test_cartesia_api_key"
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


@pytest.fixture(scope="session")
def _app_with_tables():
    """Create the Flask app and DB tables once per session."""
    from app import app as flask_app

    # Import all models so SQLAlchemy registers their tables
    import models.user_model
    import models.voice_model
    import models.audio_model
    import models.story_model
    import models.credit_model

    # Disable rate limiting for tests
    flask_app.config['RATELIMIT_ENABLED'] = False

    with flask_app.app_context():
        db.create_all()

    yield flask_app

    with flask_app.app_context():
        db.drop_all()


@pytest.fixture(autouse=True)
def _db_cleanup(_app_with_tables):
    """Truncate all tables after every test for full isolation."""
    yield
    with _app_with_tables.app_context():
        db.session.rollback()
        for table in reversed(db.metadata.sorted_tables):
            db.session.execute(table.delete())
        db.session.commit()


@pytest.fixture
def app(_app_with_tables):
    """Flask application fixture"""
    from utils.rate_limiter import limiter
    with patch('config.Config.validate', return_value=True):  # Force validation to pass
        limiter.enabled = False
        yield _app_with_tables
        limiter.enabled = True


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
def sample_stories_directory(tmp_path, monkeypatch):
    """Create sample story files for testing in a temporary directory"""
    # Create a test stories directory inside the temp directory
    test_stories_dir = tmp_path / "stories"
    test_stories_dir.mkdir()

    # Create test story files
    for i in range(1, 3):
        story_data = {
            "id": i,
            "title": f"Test Story {i}",
            "author": "Test Author",
            "description": f"Description for Test Story {i}",
            "content": f"Content for Test Story {i}"
        }

        with open(test_stories_dir / f"{i}.json", 'w') as f:
            json.dump(story_data, f)

    # Patch the Config.STORIES_DIR to use our test directory
    monkeypatch.setattr('config.Config.STORIES_DIR', test_stories_dir)

    yield test_stories_dir


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

    # Patch the ElevenLabsService create_session method
    with patch('utils.elevenlabs_service.ElevenLabsService.create_session', return_value=mock_session):
        yield mock_session


@pytest.fixture
def mock_cartesia_session():
    """Mock requests session for Cartesia API"""
    # Create a proper mock with the headers attribute as a dictionary
    mock_session = MagicMock()
    mock_session.headers = {}  # Initialize as dict, not a mock

    # Configure post method to return successful response for voice cloning
    mock_post_response = MagicMock()
    mock_post_response.status_code = 200
    mock_post_response.json.return_value = {
        "id": "test-voice-id-789",
        "name": "Test Voice",
        "user_id": "test-user-123",
        "is_public": False,
        "description": "Test voice description",
        "created_at": "2024-11-13T07:06:22.476564Z",
        "language": "pl"
    }
    mock_post_response.content = b'mock audio content'
    mock_post_response.raise_for_status.return_value = None
    mock_session.post.return_value = mock_post_response

    # Configure delete method for voice deletion
    mock_delete_response = MagicMock()
    mock_delete_response.status_code = 200
    mock_delete_response.json.return_value = {"status": "success"}
    mock_session.delete.return_value = mock_delete_response

    # Pre-populate headers so tests that check them pass
    mock_session.headers = {
        "X-API-Key": os.environ.get("CARTESIA_API_KEY", "test_cartesia_api_key"),
        "Cartesia-Version": "2024-11-13",
    }

    # Patch the CartesiaService create_session method
    with patch('utils.cartesia_service.CartesiaService.create_session', return_value=mock_session):
        yield mock_session
