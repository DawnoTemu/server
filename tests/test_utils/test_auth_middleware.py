import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch


class TestTokenIssuedAtValidation:
    @patch("controllers.voice_controller.VoiceController.get_voices_by_user", return_value=(True, [], 200))
    @patch("utils.auth_middleware.UserModel.get_by_id")
    @patch("utils.auth_middleware.jwt.decode")
    def test_allows_token_issued_in_same_second_as_user_update(
        self,
        mock_decode,
        mock_get_user,
        mock_get_voices,
        client,
    ):
        updated_at = datetime(2026, 2, 8, 6, 27, 33, 683765)
        token_iat = int(datetime(2026, 2, 8, 6, 27, 33, 900000, tzinfo=timezone.utc).timestamp())

        mock_decode.return_value = {"type": "access", "sub": 1, "iat": token_iat}
        mock_get_user.return_value = SimpleNamespace(
            id=1,
            is_active=True,
            email_confirmed=True,
            updated_at=updated_at,
        )

        response = client.get("/voices", headers={"Authorization": "Bearer test-token"})

        assert response.status_code == 200
        assert json.loads(response.data) == []
        mock_get_voices.assert_called_once_with(1)

    @patch("controllers.voice_controller.VoiceController.get_voices_by_user", return_value=(True, [], 200))
    @patch("utils.auth_middleware.UserModel.get_by_id")
    @patch("utils.auth_middleware.jwt.decode")
    def test_rejects_token_issued_before_user_update_second(
        self,
        mock_decode,
        mock_get_user,
        mock_get_voices,
        client,
    ):
        updated_at = datetime(2026, 2, 8, 6, 27, 33, 100000)
        token_iat = int(datetime(2026, 2, 8, 6, 27, 32, tzinfo=timezone.utc).timestamp())

        mock_decode.return_value = {"type": "access", "sub": 1, "iat": token_iat}
        mock_get_user.return_value = SimpleNamespace(
            id=1,
            is_active=True,
            email_confirmed=True,
            updated_at=updated_at,
        )

        response = client.get("/voices", headers={"Authorization": "Bearer test-token"})

        assert response.status_code == 401
        data = json.loads(response.data)
        assert data["error"] == "Token is no longer valid, please log in again"
        mock_get_voices.assert_not_called()
