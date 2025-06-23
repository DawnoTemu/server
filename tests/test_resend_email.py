#!/usr/bin/env python3
"""
Test script for Resend email integration with template system.

This script tests:
1. Resend API configuration
2. Email template system
3. Confirmation email sending
4. Password reset email sending
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import create_app
from utils.email_service import EmailService
from utils.email_template_helper import EmailTemplateHelper
from config import Config

def test_email_system():
    """Test the complete email system"""
    print("Testing Resend email integration with template system...")
    
    # Test configuration
    Config = EmailService._get_config()
    
    if not Config.RESEND_API_KEY:
        print("❌ RESEND_API_KEY not found in environment variables")
        return False
    
    print("✅ Resend API key found")
    print(f"📧 From email: {Config.RESEND_FROM_EMAIL}")
    print(f"🌐 Frontend URL: {Config.FRONTEND_URL}")
    
    # Initialize email service
    app = create_app()
    with app.app_context():
        EmailService.init_app(app)
        print("✅ Email service initialized")
        
        # Test template system
        print("🧪 Testing template system...")
        
        try:
            # Test base template loading
            base_template = EmailTemplateHelper.get_base_email_template(
                preheader_text="Test preheader",
                email_title="Test Email",
                email_content="<p>Test content</p>",
                button_section="<button>Test Button</button>"
            )
            print("✅ Base template loaded successfully")
            
            # Test button HTML generation
            button_html = EmailTemplateHelper.create_button_html(
                url="https://example.com",
                text="Test Button",
                icon="🚀"
            )
            print("✅ Button HTML generated successfully")
            
            # Test gradient text
            gradient_text = EmailTemplateHelper.create_gradient_text("Test Text")
            print("✅ Gradient text generated successfully")
            
        except Exception as e:
            print(f"❌ Template system error: {e}")
            return False
        
        # Test sending confirmation email
        test_email = "zespol@dawnotemu.app"
        test_token = "test_token_123"
        
        print(f"📤 Sending test confirmation email to: {test_email}")
        success = EmailService.send_confirmation_email(test_email, test_token)
        
        if success:
            print("✅ Test confirmation email sent successfully!")
        else:
            print("❌ Failed to send confirmation email")
            return False
        
        # Test sending password reset email
        print(f"📤 Sending test password reset email to: {test_email}")
        success = EmailService.send_password_reset_email(test_email, test_token)
        
        if success:
            print("✅ Test password reset email sent successfully!")
        else:
            print("❌ Failed to send password reset email")
            return False
    
    print("🎉 All email tests passed successfully!")
    return True

if __name__ == "__main__":
    success = test_email_system()
    if not success:
        sys.exit(1) 