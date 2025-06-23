#!/usr/bin/env python3
"""
Test script for Resend email integration with template system
"""
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.email_service import EmailService
from utils.email_template_helper import EmailTemplateHelper
from config import Config

def test_resend_email():
    """Test sending an email via Resend with template system"""
    print("Testing Resend email integration with template system...")
    
    # Check if API key is set
    if not Config.RESEND_API_KEY:
        print("❌ RESEND_API_KEY not found in environment variables")
        return False
    
    print(f"✅ Resend API key found")
    print(f"📧 From email: {Config.RESEND_FROM_EMAIL}")
    print(f"🌐 Frontend URL: {Config.FRONTEND_URL}")
    
    # Initialize the email service
    try:
        EmailService.init_app(None)  # We don't need Flask app for this test
        print("✅ Email service initialized")
    except Exception as e:
        print(f"❌ Failed to initialize email service: {e}")
        return False
    
    # Test template system
    print("🧪 Testing template system...")
    try:
        # Test loading base template
        template_content = EmailTemplateHelper.load_template('base_template.html')
        if template_content:
            print("✅ Base template loaded successfully")
        else:
            print("❌ Failed to load base template")
            return False
            
        # Test creating button HTML
        button_html = EmailTemplateHelper.create_button_html(
            url="https://example.com",
            text="Test Button",
            icon="🧪"
        )
        print("✅ Button HTML generated successfully")
        
        # Test gradient text
        gradient_text = EmailTemplateHelper.create_gradient_text("test gradient")
        print("✅ Gradient text generated successfully")
        
    except Exception as e:
        print(f"❌ Template system test failed: {e}")
        return False
    
    # Test sending a confirmation email
    test_email = "zespol@dawnotemu.app"
    test_token = "test_token_12345"
    
    print(f"📤 Sending test confirmation email to: {test_email}")
    
    try:
        success = EmailService.send_confirmation_email(test_email, test_token)
        if success:
            print("✅ Test confirmation email sent successfully!")
        else:
            print("❌ Failed to send test confirmation email")
            return False
    except Exception as e:
        print(f"❌ Error sending test confirmation email: {e}")
        return False
    
    # Test sending a password reset email
    print(f"📤 Sending test password reset email to: {test_email}")
    
    try:
        success = EmailService.send_password_reset_email(test_email, test_token)
        if success:
            print("✅ Test password reset email sent successfully!")
        else:
            print("❌ Failed to send test password reset email")
            return False
    except Exception as e:
        print(f"❌ Error sending test password reset email: {e}")
        return False
    
    print("🎉 All email tests passed successfully!")
    return True

if __name__ == "__main__":
    success = test_resend_email()
    sys.exit(0 if success else 1) 