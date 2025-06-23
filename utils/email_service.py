import logging
import resend
from config import Config
from utils.email_template_helper import EmailTemplateHelper

# Configure logger
logger = logging.getLogger('email_service')

class EmailService:
    """Service for sending emails using Resend API"""
    
    @staticmethod
    def init_app(app):
        """Initialize the email service with the Flask app"""
        # Set the Resend API key
        resend.api_key = Config.RESEND_API_KEY
        logger.info("Resend API initialized")
    
    @staticmethod
    def send_email(subject, recipient, text_body, html_body=None):
        """
        Send an email using Resend API
        
        Args:
            subject: Email subject
            recipient: Recipient email address
            text_body: Plain text email body
            html_body: HTML email body (optional)
        """
        try:
            # Prepare email data
            email_data = {
                "from": Config.RESEND_FROM_EMAIL,
                "to": recipient,
                "subject": subject,
                "text": text_body
            }
            
            # Add HTML body if provided
            if html_body:
                email_data["html"] = html_body
            
            # Send email via Resend
            response = resend.Emails.send(email_data)
            
            logger.info(f"Email sent to {recipient}: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {recipient}: {str(e)}")
            # Note: We can't easily access Flask app config here, so we'll just log the error
            logger.info(f"Email content that would have been sent: {text_body}")
            return False
    
    @staticmethod
    def send_confirmation_email(user_email, token):
        """
        Send account confirmation email with DawnoTemu styling
        
        Args:
            user_email: User's email address
            token: Confirmation token
        """
        # Build the confirmation URL
        confirm_url = f"{Config.FRONTEND_URL}/confirm-email/{token}"
        
        subject = "Potwierdź swoje konto DawnoTemu ✨"
        
        # Plain text version
        text_body = f"""
        Witaj w DawnoTemu!

        Dziękujemy za dołączenie do naszej społeczności! Jesteśmy podekscytowani, że będziesz mógł/mogła tworzyć magiczne chwile z bajkami opowiadanymi Twoim głosem.

        Aby aktywować swoje konto, kliknij w poniższy link:
        {confirm_url}

        Jeśli nie zakładałeś/aś konta w DawnoTemu, możesz zignorować tę wiadomość.

        Pamiętasz ten wieczór, gdy nie mogłeś/mogłaś być blisko? Teraz Twój głos zawsze będzie przy Twoim dziecku. ❤️

        Pozdrawiamy,
        Zespół DawnoTemu
        """
        
        # Create HTML content using template helper
        button_html = EmailTemplateHelper.create_button_html(
            url=confirm_url,
            text="Potwierdź konto",
            icon="✨"
        )
        
        content_html = f"""
        <p style="margin: 0 0 25px 0; color: #6C6F93; font-size: 18px; line-height: 1.6;" class="mobile-text">
            Dziękujemy za dołączenie do naszej społeczności! Jesteśmy podekscytowani, że będziesz mógł/mogła tworzyć {EmailTemplateHelper.create_gradient_text("magiczne chwile")} z bajkami opowiadanymi Twoim głosem.
        </p>
        
        <p style="margin: 0 0 30px 0; color: #6C6F93; font-size: 16px; line-height: 1.6; font-style: italic;">
            Pamiętasz ten wieczór, gdy nie mogłeś/mogłaś być blisko? Teraz Twój głos zawsze będzie przy Twoim dziecku. ❤️
        </p>
        """
        
        # Generate HTML using template helper
        html_body = EmailTemplateHelper.get_base_email_template(
            preheader_text="Potwierdź swoje konto DawnoTemu i zacznij tworzyć magiczne chwile ✨",
            email_title="Witaj w DawnoTemu! 👋",
            email_content=content_html,
            button_section=button_html
        )
        
        return EmailService.send_email(subject, user_email, text_body, html_body)
    
    @staticmethod
    def send_password_reset_email(user_email, token):
        """
        Send password reset email with DawnoTemu styling
        
        Args:
            user_email: User's email address
            token: Password reset token
        """
        # Build the reset URL
        reset_url = f"{Config.FRONTEND_URL}/reset-password/{token}"
        
        subject = "Resetuj hasło do DawnoTemu 🔐"
        
        # Plain text version
        text_body = f"""
        Witaj!

        Otrzymaliśmy prośbę o zresetowanie hasła do Twojego konta DawnoTemu.

        Aby zresetować hasło, kliknij w poniższy link:
        {reset_url}

        Jeśli nie prosiłeś/aś o reset hasła, możesz bezpiecznie zignorować tę wiadomość.

        Ten link wygaśnie za 1 godzinę.

        Pozdrawiamy,
        Zespół DawnoTemu
        """
        
        # Create HTML content using template helper
        button_html = EmailTemplateHelper.create_button_html(
            url=reset_url,
            text="Resetuj hasło",
            icon="🔐"
        )
        
        content_html = f"""
        <p style="margin: 0 0 25px 0; color: #6C6F93; font-size: 18px; line-height: 1.6;" class="mobile-text">
            Otrzymaliśmy prośbę o zresetowanie hasła do Twojego konta DawnoTemu. Nie martw się, pomożemy Ci wrócić do tworzenia {EmailTemplateHelper.create_gradient_text("magicznych chwil")} z Twoim dzieckiem.
        </p>
        
        <p style="margin: 0 0 30px 0; color: #6C6F93; font-size: 16px; line-height: 1.6; font-style: italic;">
            Jeśli nie prosiłeś/aś o reset hasła, możesz bezpiecznie zignorować tę wiadomość. Ten link wygaśnie za 1 godzinę.
        </p>
        """
        
        # Generate HTML using template helper
        html_body = EmailTemplateHelper.get_base_email_template(
            preheader_text="Resetuj hasło do DawnoTemu i wróć do tworzenia magicznych chwil 🔐",
            email_title="Resetuj hasło 🔐",
            email_content=content_html,
            button_section=button_html
        )
        
        return EmailService.send_email(subject, user_email, text_body, html_body)