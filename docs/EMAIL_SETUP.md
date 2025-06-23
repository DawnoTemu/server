# Email Configuration with Resend

This application has been configured to use the [Resend](https://resend.com) API for sending emails instead of traditional SMTP. The email system now uses a modular template system for better maintainability and reusability.

## Configuration

### Environment Variables

Add the following environment variables to your `.env` file:

```bash
# Resend API Configuration
RESEND_API_KEY=re_Jz1BJt4X_2Xp1zyCC9HCrneocNbWB1Asu
RESEND_FROM_EMAIL=no-reply@dawnotemu.app
FRONTEND_URL=https://your-frontend-domain.com
BACKEND_URL=https://your-backend-api-domain.com
```

### Required Environment Variables

- `RESEND_API_KEY`: Your Resend API key (required)
- `RESEND_FROM_EMAIL`: The sender email address (defaults to `no-reply@dawnotemu.app`)
- `FRONTEND_URL`: Your frontend application URL (defaults to `http://localhost:3000`)
- `BACKEND_URL`: Your backend API URL for email confirmation links (defaults to `http://localhost:8000`)

## Email Template System

The email system now uses a modular template architecture:

### Template Files

- `templates/email/base_template.html`: Base email template with DawnoTemu styling
- `utils/email_template_helper.py`: Helper utilities for template rendering
- `utils/email_service.py`: Main email service (now much more compact)

### Template Features

- **Reusable Base Template**: Single template file with placeholder variables
- **Helper Functions**: Utilities for creating buttons, gradient text, etc.
- **Modular Design**: Easy to add new email types without duplicating code
- **DawnoTemu Branding**: Consistent styling across all emails

### Template Variables

The base template supports these variables:

- `{{preheader_text}}`: Email preheader text
- `{{email_title}}`: Main email title
- `{{email_content}}`: Email content HTML
- `{{button_section}}`: Button/CTA section HTML

## Email Types Sent

The application sends the following types of emails:

1. **Account Confirmation Email**
   - Triggered when a user registers
   - Contains a confirmation link with token
   - Subject: "Potwierdź swoje konto DawnoTemu ✨"

2. **Password Reset Email**
   - Triggered when a user requests password reset
   - Contains a password reset link with token
   - Subject: "Resetuj hasło do DawnoTemu 🔐"

## Adding New Email Types

To add a new email type:

1. Create a new method in `EmailService` class
2. Use `EmailTemplateHelper.get_base_email_template()` to generate HTML
3. Use helper functions for buttons and gradient text:

```python
# Create a button
button_html = EmailTemplateHelper.create_button_html(
    url="https://example.com",
    text="Click Me",
    icon="🚀"
)

# Create gradient text
gradient_text = EmailTemplateHelper.create_gradient_text("special text")

# Generate full email
html_body = EmailTemplateHelper.get_base_email_template(
    preheader_text="Your custom preheader",
    email_title="Your Email Title",
    email_content=f"<p>Your content with {gradient_text}</p>",
    button_section=button_html
)
```

## Testing

To test the email integration and template system, run:

```bash
python tests/test_resend_email.py
```

This will:
- Test the template system
- Send a test confirmation email
- Send a test password reset email
- Verify all components are working correctly

## Migration from Flask-Mail

The application has been migrated from Flask-Mail to Resend API with a modular template system:

### Changes Made:
- Replaced `flask-mail` with `resend` in `requirements.txt`
- Created modular template system with separate files
- Updated `utils/email_service.py` to use template helpers
- Removed SMTP configuration from `app.py`
- Added Resend configuration to `config.py`
- Created `EmailTemplateHelper` for reusable template functions

### Benefits:
- **No SMTP Configuration**: No need to configure SMTP servers
- **Better Deliverability**: Improved email delivery rates
- **Modular Templates**: Easy to maintain and extend
- **Reusable Components**: Button, gradient text, and other helpers
- **Consistent Branding**: Single template ensures consistent styling
- **Simpler Code**: EmailService is now much more compact

## File Structure

```
templates/
  email/
    base_template.html          # Base email template
utils/
  email_service.py              # Main email service (compact)
  email_template_helper.py      # Template utilities
```

## API Endpoints

The following endpoints trigger emails:

- `POST /auth/register` → Sends confirmation email
- `POST /auth/resend-confirmation` → Resends confirmation email  
- `POST /auth/reset-password-request` → Sends password reset email

## Troubleshooting

1. **API Key Issues**: Ensure your `RESEND_API_KEY` is valid and has proper permissions
2. **Domain Verification**: Make sure your sender domain (`dawnotemu.app`) is verified in Resend
3. **Template Issues**: Check that `templates/email/base_template.html` exists and is readable
4. **Rate Limits**: Check Resend's rate limits if you're sending many emails
5. **Logs**: Check application logs for detailed error messages

## Security Notes

- API keys should be kept secure and never committed to version control
- The application uses environment variables for all sensitive configuration
- Email tokens have expiration times for security
- The application prevents email enumeration attacks
- Template files are loaded from the filesystem, ensure proper file permissions 