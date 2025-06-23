import logging
import resend
from utils.email_template_helper import EmailTemplateHelper

# Configure logger
logger = logging.getLogger('email_service')

class EmailService:
    """Service for sending emails using Resend API"""
    
    @staticmethod
    def _get_config():
        """Lazy import Config to avoid circular imports"""
        from config import Config
        return Config
    
    @staticmethod
    def init_app(app):
        """Initialize the email service with the Flask app"""
        # Set the Resend API key
        Config = EmailService._get_config()
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
            Config = EmailService._get_config()
            
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
        Config = EmailService._get_config()
        
        # Build the confirmation URL - use backend API endpoint
        confirm_url = f"{Config.BACKEND_URL}/auth/confirm-email/{token}"
        
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
        Config = EmailService._get_config()
        
        # Build the reset URL - use backend API endpoint
        reset_url = f"{Config.BACKEND_URL}/auth/reset-password/{token}"
        
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
    
    @staticmethod
    def send_email_verification_success(user_email):
        """
        Send email verification success notification with beta access information
        
        Args:
            user_email: User's email address
        """
        subject = "Email zweryfikowany! Oczekujemy na aktywację konta ✨"
        
        # Plain text version
        text_body = """
        Gratulacje!

        Twój email został pomyślnie zweryfikowany! 🎉

        DawnoTemu jest obecnie w fazie beta, dlatego Twoje konto oczekuje na weryfikację przez nasz zespół.

        Zostaniesz powiadomiony/a emailem, gdy Twoje konto zostanie aktywowane i będziesz mógł/mogła zacząć tworzyć magiczne chwile z bajkami opowiadanymi Twoim głosem.

        Dziękujemy za cierpliwość! Pracujemy nad tym, aby zapewnić najlepsze doświadczenie dla wszystkich rodziców.

        Pamiętasz ten wieczór, gdy nie mogłeś/mogłaś być blisko? Wkrótce Twój głos zawsze będzie przy Twoim dziecku. ❤️

        Pozdrawiamy,
        Zespół DawnoTemu
        """
        
        # Create HTML content using template helper
        content_html = f"""
        <div style="background-color: #F9FAFC; padding: 30px; border-radius: 16px; border: 1px solid rgba(229, 231, 235, 0.5); margin-bottom: 30px; text-align: center;">
            <div style="width: 60px; height: 60px; background: linear-gradient(135deg, #63E6E2 0%, #4FD1C7 100%); border-radius: 50%; margin: 0 auto 20px auto; display: flex; align-items: center; justify-content: center; font-size: 24px; color: #FFFFFF;">
                ✅
            </div>
            <h3 style="margin: 0 0 15px 0; color: #2D3047; font-size: 20px; font-weight: 700;">
                Email pomyślnie zweryfikowany!
            </h3>
            <p style="margin: 0; color: #6C6F93; font-size: 16px; line-height: 1.6;">
                Gratulacje! Twój adres email został potwierdzony.
            </p>
        </div>
        
        <p style="margin: 0 0 25px 0; color: #6C6F93; font-size: 18px; line-height: 1.6;" class="mobile-text">
            DawnoTemu jest obecnie w {EmailTemplateHelper.create_gradient_text("fazie beta")}, dlatego Twoje konto oczekuje na weryfikację przez nasz zespół.
        </p>
        
        <div style="background-color: rgba(218, 143, 255, 0.1); padding: 25px; border-radius: 16px; border-left: 4px solid #DA8FFF; margin-bottom: 25px;">
            <p style="margin: 0 0 15px 0; color: #2D3047; font-size: 16px; line-height: 1.6; font-weight: 600;">
                🚀 Co dalej?
            </p>
            <p style="margin: 0; color: #6C6F93; font-size: 16px; line-height: 1.6;">
                <strong>Zostaniesz powiadomiony/a emailem</strong>, gdy Twoje konto zostanie aktywowane i będziesz mógł/mogła zacząć tworzyć magiczne chwile z bajkami opowiadanymi Twoim głosem.
            </p>
        </div>
        
        <p style="margin: 0 0 30px 0; color: #6C6F93; font-size: 16px; line-height: 1.6; font-style: italic;">
            Pamiętasz ten wieczór, gdy nie mogłeś/mogłaś być blisko? Wkrótce Twój głos zawsze będzie przy Twoim dziecku. ❤️
        </p>
        
        <div style="background-color: rgba(251, 190, 159, 0.1); padding: 20px; border-radius: 12px; text-align: center;">
            <p style="margin: 0; color: #2D3047; font-size: 14px; font-style: italic;">
                💜 Dziękujemy za cierpliwość! Pracujemy nad tym, aby zapewnić najlepsze doświadczenie dla wszystkich rodziców.
            </p>
        </div>
        """
        
        # Generate HTML using template helper
        html_body = EmailTemplateHelper.get_base_email_template(
            preheader_text="Email zweryfikowany! Oczekujemy na aktywację konta w fazie beta ✨",
            email_title="Email zweryfikowany! 🎉",
            email_content=content_html,
            button_section=""
        )
        
        return EmailService.send_email(subject, user_email, text_body, html_body)