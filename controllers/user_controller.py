import logging
from typing import Optional

from database import db
from models.user_model import UserModel, User
from utils.email_service import EmailService

logger = logging.getLogger(__name__)


class UserController:
    """Controller for authenticated user profile operations."""

    @staticmethod
    def update_profile(
        user: User,
        *,
        current_password: Optional[str],
        new_email: Optional[str] = None,
        new_password: Optional[str] = None,
        new_password_confirm: Optional[str] = None,
    ):
        """
        Update the authenticated user's profile details.

        Args:
            user: The current authenticated user instance.
            current_password: Password to verify before applying changes.
            new_email: New email address (optional).
            new_password: New password (optional).
            new_password_confirm: Confirmation of the new password.

        Returns:
            tuple: (success, payload, status_code)
        """
        if not current_password:
            return False, {"error": "Current password is required to update your profile."}, 400

        if not user.check_password(current_password):
            return False, {"error": "Current password is incorrect."}, 403

        if not new_email and not new_password:
            return False, {"error": "Provide a new email and/or password to update your profile."}, 400

        email_changed = False
        password_changed = False

        try:
            if new_email:
                candidate_email = new_email.strip()
                if candidate_email and candidate_email.lower() != (user.email or "").lower():
                    existing_user = UserModel.get_by_email(candidate_email)
                    if existing_user and existing_user.id != user.id:
                        return False, {"error": "Email is already in use by another account."}, 409

                    user.email = candidate_email
                    user.email_confirmed = False
                    email_changed = True

            if new_password:
                if not new_password_confirm:
                    return False, {"error": "New password confirmation is required."}, 400
                if new_password != new_password_confirm:
                    return False, {"error": "New password and confirmation do not match."}, 400
                if user.check_password(new_password):
                    return False, {"error": "New password must be different from the current password."}, 400

                user.set_password(new_password)
                password_changed = True

            if not email_changed and not password_changed:
                return False, {"error": "No changes detected. Submit a different email or password to update your profile."}, 400

            db.session.commit()
        except Exception as exc:
            logger.exception("Failed updating profile for user %s", user.id)
            db.session.rollback()
            return False, {"error": "Unable to update profile at this time."}, 500

        response = {
            "user": user.to_dict(),
            "message": "Profile updated successfully.",
            "email_confirmation_required": False,
            "password_updated": password_changed,
        }

        if email_changed:
            response["email_confirmation_required"] = True

            try:
                token = user.get_confirmation_token()
                EmailService.send_confirmation_email(user.email, token)
            except Exception as exc:
                logger.warning(
                    "Updated email for user %s but failed to send confirmation email: %s",
                    user.id,
                    exc,
                )
                response["email_confirmation_error"] = "Updated email but failed to send confirmation email. Please contact support if you do not receive it shortly."

        return True, response, 200

    @staticmethod
    def delete_account(user: User, *, current_password: Optional[str]):
        """
        Delete the authenticated user's account.

        Args:
            user: The current authenticated user instance.
            current_password: Password to verify before deleting the account.

        Returns:
            tuple: (success, payload, status_code)
        """
        if not current_password:
            return False, {"error": "Current password is required to delete your account."}, 400

        if not user.check_password(current_password):
            return False, {"error": "Current password is incorrect."}, 403

        success, details = UserModel.delete_user(user.id)
        if not success:
            return False, {
                "error": "Unable to delete account at this time.",
                "details": details
            }, 500

        response = {
            "message": "Your account has been deleted.",
        }

        warnings = details.get("warnings") if isinstance(details, dict) else None
        if warnings:
            response["warnings"] = warnings

        return True, response, 200
