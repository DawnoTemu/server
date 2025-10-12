import json
from types import SimpleNamespace
from unittest.mock import patch


class TestAudioRoutes:
    """Tests for the audio routes supporting both external and internal voice IDs."""

    @patch("utils.auth_middleware.UserModel.get_by_id", return_value=SimpleNamespace(id=1, is_active=True, email_confirmed=True))
    @patch("utils.auth_middleware.jwt.decode", return_value={"type": "access", "sub": 1})
    def test_get_audio_success_external_id(self, mock_jwt, mock_user, client):
        voice = SimpleNamespace(id=5, user_id=1)
        with patch("models.voice_model.VoiceModel.get_voice_by_elevenlabs_id", return_value=voice) as mock_get_external, \
             patch("models.voice_model.VoiceModel.get_voice_by_id", return_value=None) as mock_get_internal, \
             patch("controllers.audio_controller.AudioController.get_audio") as mock_get_audio:
            mock_get_audio.return_value = (True, b"audio-bytes", 200, {"content_length": 11})

            response = client.get(
                "/voices/ext-voice-123/stories/13/audio",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        assert response.data == b"audio-bytes"
        assert response.headers.get("Content-Length") == "11"
        mock_get_external.assert_called_once_with("ext-voice-123")
        mock_get_internal.assert_not_called()
        mock_get_audio.assert_called_once_with(voice.id, 13, None)

    @patch("utils.auth_middleware.UserModel.get_by_id", return_value=SimpleNamespace(id=1, is_active=True, email_confirmed=True))
    @patch("utils.auth_middleware.jwt.decode", return_value={"type": "access", "sub": 1})
    def test_get_audio_success_internal_id_fallback(self, mock_jwt, mock_user, client):
        voice = SimpleNamespace(id=7, user_id=1)
        with patch("models.voice_model.VoiceModel.get_voice_by_elevenlabs_id", return_value=None) as mock_get_external, \
             patch("models.voice_model.VoiceModel.get_voice_by_id", return_value=voice) as mock_get_internal, \
             patch("controllers.audio_controller.AudioController.get_audio") as mock_get_audio:
            mock_get_audio.return_value = (True, b"audio", 200, {})

            response = client.get(
                "/voices/7/stories/42/audio",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        mock_get_external.assert_called_once_with("7")
        mock_get_internal.assert_called_once_with(7)
        mock_get_audio.assert_called_once_with(voice.id, 42, None)

    @patch("utils.auth_middleware.UserModel.get_by_id", return_value=SimpleNamespace(id=1, is_active=True, email_confirmed=True))
    @patch("utils.auth_middleware.jwt.decode", return_value={"type": "access", "sub": 1})
    def test_get_audio_redirect(self, mock_jwt, mock_user, client):
        voice = SimpleNamespace(id=6, user_id=1)
        with patch("models.voice_model.VoiceModel.get_voice_by_elevenlabs_id", return_value=voice), \
             patch("models.voice_model.VoiceModel.get_voice_by_id", return_value=None), \
             patch("controllers.audio_controller.AudioController.get_audio_presigned_url", return_value=(True, "https://cdn/audio.mp3", 200)) as mock_presign:
            response = client.get(
                "/voices/ext-voice/stories/21/audio?redirect=1",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 302
        assert response.location == "https://cdn/audio.mp3"
        mock_presign.assert_called_once_with(voice.id, 21, expires_in=3600)

    @patch("utils.auth_middleware.UserModel.get_by_id", return_value=SimpleNamespace(id=1, is_active=True, email_confirmed=True))
    @patch("utils.auth_middleware.jwt.decode", return_value={"type": "access", "sub": 1})
    def test_get_audio_unauthorized(self, mock_jwt, mock_user, client):
        voice = SimpleNamespace(id=9, user_id=2)
        with patch("models.voice_model.VoiceModel.get_voice_by_elevenlabs_id", return_value=voice), \
             patch("models.voice_model.VoiceModel.get_voice_by_id", return_value=None):
            response = client.get(
                "/voices/ext-voice-unauth/stories/14/audio",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 403

    @patch("utils.auth_middleware.UserModel.get_by_id", return_value=SimpleNamespace(id=1, is_active=True, email_confirmed=True))
    @patch("utils.auth_middleware.jwt.decode", return_value={"type": "access", "sub": 1})
    def test_check_audio_exists(self, mock_jwt, mock_user, client):
        from routes import audio_routes
        voice = SimpleNamespace(id=3, user_id=1)
        current_user = SimpleNamespace(id=1)
        with client.application.test_request_context(
            "/voices/ext-voice-check/stories/5/audio",
            method="HEAD",
            headers={"Authorization": "Bearer test-token"},
        ), \
            patch("routes.audio_routes._resolve_voice_for_user", return_value=(voice, None)), \
            patch("controllers.audio_controller.AudioController.check_audio_exists", return_value=(True, {"exists": True}, 200)) as mock_check:
            body, status = audio_routes.check_audio_exists.__wrapped__(current_user, "ext-voice-check", 5)

        assert mock_check.call_count == 1
        mock_check.assert_called_once_with(voice.id, 5)
        assert status == 200
        assert body == ""

    @patch("utils.auth_middleware.UserModel.get_by_id", return_value=SimpleNamespace(id=1, is_active=True, email_confirmed=True))
    @patch("utils.auth_middleware.jwt.decode", return_value={"type": "access", "sub": 1})
    def test_synthesize_audio_route(self, mock_jwt, mock_user, client):
        voice = SimpleNamespace(id=11, user_id=1)
        with patch("models.voice_model.VoiceModel.get_voice_by_elevenlabs_id", return_value=None), \
             patch("models.voice_model.VoiceModel.get_voice_by_id", return_value=voice), \
             patch("controllers.audio_controller.AudioController.synthesize_audio") as mock_synthesize:
            mock_synthesize.return_value = (
                True,
                {"status": "processing", "id": 77, "voice": {"queue_position": 2, "queue_length": 5}},
                202,
            )

            response = client.post(
                "/voices/11/stories/17/audio",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 202
        data = json.loads(response.data)
        assert data["status"] == "processing"
        mock_synthesize.assert_called_once_with(voice.id, 17)
        assert response.headers.get("X-Voice-Queue-Position") == "2"
        assert response.headers.get("X-Voice-Queue-Length") == "5"
