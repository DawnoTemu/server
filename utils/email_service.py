from flask import current_app, render_template
from flask_mail import Message, Mail
import logging

# Configure logger
logger = logging.getLogger('email_service')

# Initialize mail object
mail = Mail()

class EmailService:
    """Service for sending emails"""
    
    @staticmethod
    def init_app(app):
        """Initialize the mail service with the Flask app"""
        mail.init_app(app)
    
    @staticmethod
    def send_email(subject, recipient, text_body, html_body=None):
        """
        Send an email
        
        Args:
            subject: Email subject
            recipient: Recipient email address
            text_body: Plain text email body
            html_body: HTML email body (optional)
        """
        try:
            msg = Message(
                subject=subject,
                recipients=[recipient],
                body=text_body,
                html=html_body,
                sender=current_app.config['MAIL_DEFAULT_SENDER']
            )
            
            mail.send(msg)
            logger.info(f"Email sent to {recipient}: {subject}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {recipient}: {str(e)}")
            # If we're in testing or development, log email content
            if current_app.config.get('TESTING') or current_app.config.get('DEBUG'):
                logger.info(f"Email content that would have been sent: {text_body}")
            return False
    
    @staticmethod
    def send_confirmation_email(user_email, token):
        """
        Send account confirmation email
        
        Args:
            user_email: User's email address
            token: Confirmation token
        """
        # Build the confirmation URL
        confirm_url = f"{current_app.config['FRONTEND_URL']}/confirm-email/{token}"
        
        subject = "Confirm Your StoryVoice Account"
        
        text_body = f"""
        Hello,

        Thank you for registering with StoryVoice!

        Please confirm your email address by clicking on the following link:
        {confirm_url}

        If you did not register for StoryVoice, please ignore this email.

        Best regards,
        The StoryVoice Team
        """
        
        html_body = f"""
        <p>Hello,</p>
        <p>Thank you for registering with StoryVoice!</p>
        <p>Please confirm your email address by clicking on the following link:</p>
        <p><a href="{confirm_url}">Confirm Email Address</a></p>
        <p>If you did not register for StoryVoice, please ignore this email.</p>
        <p>Best regards,<br>The StoryVoice Team</p>
        """
        
        return EmailService.send_email(subject, user_email, text_body, html_body)
    
    @staticmethod
    def send_password_reset_email(user_email, token):
        """
        Send password reset email
        
        Args:
            user_email: User's email address
            token: Password reset token
        """
        # Build the reset URL
        reset_url = f"{current_app.config['FRONTEND_URL']}/reset-password/{token}"
        
        subject = "Reset Your StoryVoice Password"
        
        text_body = f"""
        Hello,

        You requested to reset your password for StoryVoice.

        Please click on the following link to reset your password:
        {reset_url}

        If you did not request a password reset, please ignore this email.

        This link will expire in 1 hour.

        Best regards,
        The StoryVoice Team
        """
        
        html_body = f"""
        <p>Hello,</p>
        <p>You requested to reset your password for StoryVoice.</p>
        <p>Please click on the following link to reset your password:</p>
        <p><a href="{reset_url}">Reset Password</a></p>
        <p>If you did not request a password reset, please ignore this email.</p>
        <p>This link will expire in 1 hour.</p>
        <p>Best regards,<br>The StoryVoice Team</p>
        """
        
        return EmailService.send_email(subject, user_email, text_body, html_body)