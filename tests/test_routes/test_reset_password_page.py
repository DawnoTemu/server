from unittest.mock import patch


def test_reset_password_get_renders_html_form(client):
    response = client.get("/auth/reset-password/sample-token")

    assert response.status_code == 200
    assert response.content_type == "text/html; charset=utf-8"
    assert b"Resetuj haslo" in response.data or b"Resetuj has\xc5\x82o" in response.data
    assert b"name=\"new_password\"" in response.data
    assert b"name=\"new_password_confirm\"" in response.data


@patch("controllers.auth_controller.AuthController.reset_password")
def test_reset_password_post_form_renders_success(mock_reset_password, client):
    mock_reset_password.return_value = (
        True,
        {"message": "Password reset successfully"},
        200,
    )

    response = client.post(
        "/auth/reset-password/sample-token",
        data={
            "new_password": "Password123",
            "new_password_confirm": "Password123",
        },
    )

    assert response.status_code == 200
    assert response.content_type == "text/html; charset=utf-8"
    assert b"Haslo zostalo zresetowane" in response.data or b"Has\xc5\x82o zosta\xc5\x82o zresetowane" in response.data
    mock_reset_password.assert_called_once_with(
        "sample-token",
        "Password123",
        "Password123",
    )
