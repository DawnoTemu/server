"""
Integration tests for REST API endpoints.

Converted from the standalone test_endpoints.py script to proper pytest tests
using the Flask test client and controller-level mocking.
"""

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch


def _fake_user():
    return SimpleNamespace(
        id=1,
        is_active=True,
        email_confirmed=True,
        to_dict=lambda: {"id": 1, "email": "test@example.com", "is_active": True},
    )


# Common auth mock decorators
_mock_jwt = patch(
    "utils.auth_middleware.jwt.decode",
    return_value={"type": "access", "sub": 1},
)
_mock_user = patch(
    "utils.auth_middleware.UserModel.get_by_id",
    return_value=_fake_user(),
)


def _auth_headers():
    return {"Authorization": "Bearer test-token"}


class TestAuthEndpoints:
    """Tests for authentication endpoints."""

    @patch("controllers.auth_controller.AuthController.register")
    def test_register_user(self, mock_register, client):
        mock_register.return_value = (
            True,
            {"message": "User registered successfully", "user_id": 1},
            201,
        )

        response = client.post(
            "/auth/register",
            json={
                "email": "test_user@example.com",
                "password": "Test@Password123",
                "password_confirm": "Test@Password123",
            },
        )

        assert response.status_code == 201
        data = response.get_json()
        assert "message" in data
        mock_register.assert_called_once()

    @patch("controllers.auth_controller.AuthController.register")
    def test_register_user_conflict(self, mock_register, client):
        mock_register.return_value = (
            False,
            {"error": "Email already registered"},
            409,
        )

        response = client.post(
            "/auth/register",
            json={
                "email": "existing@example.com",
                "password": "Test@Password123",
                "password_confirm": "Test@Password123",
            },
        )

        assert response.status_code == 409

    @patch("controllers.auth_controller.AuthController.login")
    def test_login(self, mock_login, client):
        mock_login.return_value = (
            True,
            {
                "access_token": "test-access-token",
                "refresh_token": "test-refresh-token",
            },
            200,
        )

        response = client.post(
            "/auth/login",
            json={
                "email": "test_user@example.com",
                "password": "Test@Password123",
            },
        )

        assert response.status_code == 200
        data = response.get_json()
        assert "access_token" in data
        assert "refresh_token" in data
        mock_login.assert_called_once()

    @_mock_user
    @_mock_jwt
    def test_get_current_user(self, mock_jwt, mock_get_user, client):
        response = client.get("/auth/me", headers=_auth_headers())

        assert response.status_code == 200
        data = response.get_json()
        assert "id" in data

    @patch("controllers.auth_controller.AuthController.refresh_token")
    def test_refresh_token(self, mock_refresh, client):
        mock_refresh.return_value = (
            True,
            {"access_token": "new-access-token"},
            200,
        )

        response = client.post(
            "/auth/refresh",
            json={"refresh_token": "test-refresh-token"},
        )

        assert response.status_code == 200
        data = response.get_json()
        assert "access_token" in data
        mock_refresh.assert_called_once()


class TestStoryEndpoints:
    """Tests for story listing and detail endpoints."""

    @patch("controllers.story_controller.StoryController.get_all_stories")
    def test_list_stories(self, mock_get_all, client):
        mock_get_all.return_value = (
            True,
            [
                {"id": 1, "title": "Story 1", "required_credits": 3},
                {"id": 2, "title": "Story 2", "required_credits": 1},
            ],
            200,
        )

        response = client.get("/stories")

        assert response.status_code == 200
        data = response.get_json()
        assert len(data) == 2
        assert data[0]["id"] == 1
        assert "required_credits" in data[0]

    @patch("controllers.story_controller.StoryController.get_story")
    def test_get_story(self, mock_get_story, client):
        mock_get_story.return_value = (
            True,
            {"id": 1, "title": "Test Story", "required_credits": 2},
            200,
        )

        response = client.get("/stories/1")

        assert response.status_code == 200
        data = response.get_json()
        assert data["id"] == 1
        assert "required_credits" in data

    @patch("controllers.story_controller.StoryController.get_story")
    def test_get_story_not_found(self, mock_get_story, client):
        mock_get_story.return_value = (
            False,
            {"error": "Story not found"},
            404,
        )

        response = client.get("/stories/999")

        assert response.status_code == 404


class TestVoiceEndpoints:
    """Tests for voice management endpoints."""

    @_mock_user
    @_mock_jwt
    @patch("controllers.voice_controller.VoiceController.clone_voice")
    def test_clone_voice(self, mock_clone, mock_jwt, mock_get_user, client):
        mock_clone.return_value = (
            True,
            {
                "id": 1,
                "name": "Test Voice",
                "status": "recorded",
                "success": True,
                "message": "Voice uploaded successfully.",
            },
            201,
        )

        response = client.post(
            "/voices",
            data={
                "file": (BytesIO(b"fake wav data"), "test.wav"),
                "name": "Test Voice",
            },
            content_type="multipart/form-data",
            headers=_auth_headers(),
        )

        assert response.status_code == 201
        data = response.get_json()
        assert data["id"] == 1
        assert data["name"] == "Test Voice"
        mock_clone.assert_called_once()

    @_mock_user
    @_mock_jwt
    @patch("controllers.voice_controller.VoiceController.get_voices_by_user")
    def test_list_voices(self, mock_get_voices, mock_jwt, mock_get_user, client):
        mock_get_voices.return_value = (
            True,
            [{"id": 1, "name": "Test Voice", "status": "recorded"}],
            200,
        )

        response = client.get("/voices", headers=_auth_headers())

        assert response.status_code == 200
        data = response.get_json()
        assert len(data) == 1
        assert data[0]["name"] == "Test Voice"
        mock_get_voices.assert_called_once()

    @_mock_user
    @_mock_jwt
    @patch("controllers.voice_controller.VoiceController.get_voice")
    def test_get_voice(self, mock_get_voice, mock_jwt, mock_get_user, client):
        mock_get_voice.return_value = (
            True,
            {
                "id": 1,
                "user_id": 1,
                "name": "Test Voice",
                "elevenlabs_voice_id": "el-voice-123",
            },
            200,
        )

        response = client.get("/voices/1", headers=_auth_headers())

        assert response.status_code == 200
        data = response.get_json()
        assert data["id"] == 1
        assert "elevenlabs_voice_id" in data

    @_mock_user
    @_mock_jwt
    @patch("controllers.voice_controller.VoiceController.get_voice_sample_url")
    @patch("controllers.voice_controller.VoiceController.get_voice")
    def test_get_voice_sample(self, mock_get_voice, mock_get_sample, mock_jwt, mock_get_user, client):
        mock_get_voice.return_value = (
            True,
            {"id": 1, "user_id": 1, "name": "Test Voice"},
            200,
        )
        mock_get_sample.return_value = (
            True,
            {"url": "https://s3.example.com/sample.wav"},
            200,
        )

        response = client.get(
            "/voices/1/sample?redirect=1", headers=_auth_headers()
        )

        assert response.status_code == 302
        mock_get_sample.assert_called_once()

    @_mock_user
    @_mock_jwt
    @patch("controllers.voice_controller.VoiceController.delete_voice")
    @patch("controllers.voice_controller.VoiceController.get_voice")
    def test_delete_voice(self, mock_get_voice, mock_delete, mock_jwt, mock_get_user, client):
        mock_get_voice.return_value = (
            True,
            {"id": 1, "user_id": 1, "name": "Test Voice"},
            200,
        )
        mock_delete.return_value = (
            True,
            {"message": "Voice deleted successfully"},
            200,
        )

        response = client.delete("/voices/1", headers=_auth_headers())

        assert response.status_code == 200
        data = response.get_json()
        assert "message" in data
        mock_delete.assert_called_once()


class TestAudioEndpoints:
    """Tests for audio synthesis and retrieval endpoints."""

    @_mock_user
    @_mock_jwt
    def test_check_audio_exists(self, mock_jwt, mock_get_user, client):
        """HEAD requests are routed through the GET handler by Flask."""
        voice = SimpleNamespace(id=1, user_id=1)
        with patch(
            "models.voice_model.VoiceModel.get_voice_by_identifier",
            return_value=voice,
        ), patch(
            "controllers.audio_controller.AudioController.get_audio",
            return_value=(True, b"", 200, {}),
        ):
            response = client.head(
                "/voices/el-voice-123/stories/1/audio",
                headers=_auth_headers(),
            )

        assert response.status_code == 200

    @_mock_user
    @_mock_jwt
    def test_synthesize_audio(self, mock_jwt, mock_get_user, client):
        voice = SimpleNamespace(id=1, user_id=1)
        with patch(
            "models.voice_model.VoiceModel.get_voice_by_identifier",
            return_value=voice,
        ), patch(
            "controllers.audio_controller.AudioController.synthesize_audio",
            return_value=(
                True,
                {"status": "processing", "task_id": "task-123"},
                200,
            ),
        ) as mock_synth:
            response = client.post(
                "/voices/el-voice-123/stories/1/audio",
                headers=_auth_headers(),
            )

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "processing"
        mock_synth.assert_called_once()

    @_mock_user
    @_mock_jwt
    def test_get_audio(self, mock_jwt, mock_get_user, client):
        voice = SimpleNamespace(id=1, user_id=1)
        with patch(
            "models.voice_model.VoiceModel.get_voice_by_identifier",
            return_value=voice,
        ), patch(
            "controllers.audio_controller.AudioController.get_audio",
            return_value=(True, b"audio-bytes", 200, {"content_length": 11}),
        ):
            response = client.get(
                "/voices/el-voice-123/stories/1/audio",
                headers=_auth_headers(),
            )

        assert response.status_code == 200
        assert response.data == b"audio-bytes"

    @_mock_user
    @_mock_jwt
    def test_get_audio_redirect(self, mock_jwt, mock_get_user, client):
        voice = SimpleNamespace(id=1, user_id=1)
        with patch(
            "models.voice_model.VoiceModel.get_voice_by_identifier",
            return_value=voice,
        ), patch(
            "controllers.audio_controller.AudioController.get_audio_presigned_url",
            return_value=(True, "https://cdn.example.com/audio.mp3", 200),
        ):
            response = client.get(
                "/voices/el-voice-123/stories/1/audio?redirect=1",
                headers=_auth_headers(),
            )

        assert response.status_code == 302
        assert response.location == "https://cdn.example.com/audio.mp3"

    @_mock_user
    @_mock_jwt
    def test_get_audio_voice_not_found(self, mock_jwt, mock_get_user, client):
        with patch(
            "models.voice_model.VoiceModel.get_voice_by_identifier",
            return_value=None,
        ):
            response = client.get(
                "/voices/nonexistent/stories/1/audio",
                headers=_auth_headers(),
            )

        assert response.status_code == 404
