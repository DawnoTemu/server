from datetime import timedelta

import pytest

from controllers.auth_controller import AuthController
from database import db
from models.user_model import User, UserModel


def _create_active_user(app, email="user@example.com", password="CurrentPass1!"):
    """Helper to create an active, confirmed user for tests."""
    with app.app_context():
        user = User(
            email=email,
            is_active=True,
            email_confirmed=True,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        access_token = AuthController.generate_access_token(
            user, expires_delta=timedelta(minutes=30)
        )

        return user.id, access_token


def _cleanup_user(app, user_id):
    with app.app_context():
        user = UserModel.get_by_id(user_id)
        if user:
            db.session.delete(user)
            db.session.commit()


def test_update_profile_email_success(client, app, mocker):
    user_id, token = _create_active_user(app)
    mock_send_email = mocker.patch(
        "utils.email_service.EmailService.send_confirmation_email", return_value=None
    )

    response = client.patch(
        "/auth/me",
        json={
            "email": "new-user@example.com",
            "current_password": "CurrentPass1!",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["user"]["email"] == "new-user@example.com"
    assert data["email_confirmation_required"] is True
    assert data["password_updated"] is False
    mock_send_email.assert_called_once()

    with app.app_context():
        refreshed_user = UserModel.get_by_id(user_id)
        assert refreshed_user.email == "new-user@example.com"
        assert refreshed_user.email_confirmed is False

    _cleanup_user(app, user_id)


def test_update_profile_password_success(client, app, mocker):
    user_id, token = _create_active_user(app)
    mock_send_email = mocker.patch(
        "utils.email_service.EmailService.send_confirmation_email", return_value=None
    )

    response = client.patch(
        "/auth/me",
        json={
            "current_password": "CurrentPass1!",
            "new_password": "NewPass123!",
            "new_password_confirm": "NewPass123!",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["email_confirmation_required"] is False
    assert data["password_updated"] is True
    mock_send_email.assert_not_called()

    with app.app_context():
        refreshed_user = UserModel.get_by_id(user_id)
        assert refreshed_user.check_password("NewPass123!")

    _cleanup_user(app, user_id)


def test_update_profile_requires_current_password(client, app):
    user_id, token = _create_active_user(app)

    response = client.patch(
        "/auth/me",
        json={"email": "missing-pass@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    data = response.get_json()
    assert "Current password is required" in data["error"]

    _cleanup_user(app, user_id)


def test_update_profile_with_wrong_password(client, app):
    user_id, token = _create_active_user(app)

    response = client.patch(
        "/auth/me",
        json={
            "email": "wrong-pass@example.com",
            "current_password": "WrongPassword!",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    data = response.get_json()
    assert "incorrect" in data["error"].lower()

    _cleanup_user(app, user_id)


def test_update_profile_duplicate_email(client, app):
    existing_user_id, _ = _create_active_user(app, email="existing@example.com")
    user_id, token = _create_active_user(app, email="primary@example.com")

    response = client.patch(
        "/auth/me",
        json={
            "email": "existing@example.com",
            "current_password": "CurrentPass1!",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409
    data = response.get_json()
    assert "already in use" in data["error"]

    _cleanup_user(app, user_id)
    _cleanup_user(app, existing_user_id)


def test_delete_profile_success(client, app, mocker):
    user_id, token = _create_active_user(app)
    mock_delete_user = mocker.patch(
        "models.user_model.UserModel.delete_user",
        return_value=(True, {"warnings": []}),
    )

    response = client.delete(
        "/auth/me",
        json={"current_password": "CurrentPass1!", "reason": "cleanup"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert "Your account has been deleted." in data["message"]
    mock_delete_user.assert_called_once_with(user_id)

    _cleanup_user(app, user_id)


def test_delete_profile_requires_current_password(client, app):
    user_id, token = _create_active_user(app)

    response = client.delete(
        "/auth/me",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    data = response.get_json()
    assert "Current password is required" in data["error"]

    _cleanup_user(app, user_id)


def test_delete_profile_with_wrong_password(client, app, mocker):
    user_id, token = _create_active_user(app)
    mock_delete_user = mocker.patch("models.user_model.UserModel.delete_user")

    response = client.delete(
        "/auth/me",
        json={"current_password": "WrongPassword!"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    data = response.get_json()
    assert "incorrect" in data["error"].lower()
    mock_delete_user.assert_not_called()

    _cleanup_user(app, user_id)


def test_delete_profile_backend_failure(client, app, mocker):
    user_id, token = _create_active_user(app)
    mocker.patch(
        "models.user_model.UserModel.delete_user",
        return_value=(False, "database down"),
    )

    response = client.delete(
        "/auth/me",
        json={"current_password": "CurrentPass1!"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 500
    data = response.get_json()
    assert "Unable to delete account" in data["error"]

    _cleanup_user(app, user_id)
