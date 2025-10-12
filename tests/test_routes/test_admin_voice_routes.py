import json
from types import SimpleNamespace
from unittest.mock import patch


class TestAdminVoiceSlotRoutes:
    """Tests for admin endpoints that surface voice slot status."""

    @patch("controllers.admin_controller.AdminController.get_voice_slot_status")
    @patch("utils.auth_middleware.UserModel.get_by_id", return_value=SimpleNamespace(
        id=1, is_active=True, email_confirmed=True, is_admin=True
    ))
    @patch("utils.auth_middleware.jwt.decode", return_value={"type": "access", "sub": 1})
    def test_voice_slot_status_endpoint(self, mock_jwt, mock_user, mock_status, client):
        mock_status.return_value = (True, {"metrics": {"ready_count": 1}}, 200)

        response = client.get(
            "/admin/voice-slots/status",
            headers={"Authorization": "Bearer admin-token"},
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["metrics"]["ready_count"] == 1
        mock_status.assert_called_once()

    @patch("controllers.admin_controller.AdminController.trigger_voice_queue_processing")
    @patch("utils.auth_middleware.UserModel.get_by_id", return_value=SimpleNamespace(
        id=1, is_active=True, email_confirmed=True, is_admin=True
    ))
    @patch("utils.auth_middleware.jwt.decode", return_value={"type": "access", "sub": 1})
    def test_voice_slot_process_queue_endpoint(self, mock_jwt, mock_user, mock_trigger, client):
        mock_trigger.return_value = (True, {"message": "triggered"}, 202)

        response = client.post(
            "/admin/voice-slots/process-queue",
            headers={"Authorization": "Bearer admin-token"},
        )

        assert response.status_code == 202
        data = json.loads(response.data)
        assert data["message"] == "triggered"
        mock_trigger.assert_called_once()
