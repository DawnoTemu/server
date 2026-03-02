from unittest.mock import patch, MagicMock

from config import Config


def test_allowed_extensions_contains_audio_formats():
    assert {"wav", "mp3", "m4a"}.issubset(Config.ALLOWED_EXTENSIONS)


def test_get_s3_client_delegates_to_s3client():
    fake = MagicMock(name="s3client")
    with patch("config.S3Client.get_client", return_value=fake) as mock_get:
        client = Config.get_s3_client()
    assert client is fake
    mock_get.assert_called_once()
