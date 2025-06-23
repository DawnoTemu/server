import pytest
from unittest.mock import MagicMock, patch
from bs4 import BeautifulSoup
from models.user_model import UserModel
from database import db

def test_confirm_email_renders_html(client, mocker):
    """
    Tests that confirming an email renders the correct HTML page.
    """
    # Clean up user if it exists from a previous run
    with client.application.app_context():
        existing_user = UserModel.get_by_email("test-html@example.com")
        if existing_user:
            db.session.delete(existing_user)
            db.session.commit()

    # 1. Mock the email service to capture the confirmation token
    mock_send_email = MagicMock()
    mocker.patch('utils.email_service.EmailService.send_confirmation_email', mock_send_email)

    # 2. Register a new user
    register_data = {
        "email": "test-html@example.com",
        "password": "Password123",
        "password_confirm": "Password123"
    }
    response = client.post('/auth/register', json=register_data)
    # The user might already exist if a previous cleanup failed.
    # A 409 is acceptable here, as we only need the confirmation token.
    assert response.status_code in [201, 409]

    # If the user was just created, a new email was sent.
    # If the user already existed, we need to trigger the email resend logic
    # to get a valid token for our test.
    if response.status_code == 409:
        resend_response = client.post('/auth/resend-confirmation', json={"email": "test-html@example.com"})
        assert resend_response.status_code == 200

    # 3. Extract the token from the mocked email call
    assert mock_send_email.called
    call_args, call_kwargs = mock_send_email.call_args
    email_arg = call_args[0]
    token_arg = call_args[1]
    assert email_arg == "test-html@example.com"
    assert token_arg is not None

    # 4. Make a GET request to the confirmation URL
    confirm_response = client.get(f'/auth/confirm-email/{token_arg}')

    # 5. Assert the response is the correct HTML page
    assert confirm_response.status_code == 200
    assert confirm_response.content_type == 'text/html; charset=utf-8'

    # 6. Parse the HTML and check for key content
    soup = BeautifulSoup(confirm_response.data, 'html.parser')
    
    # Check for the logo
    logo = soup.find('img', {'alt': 'DawnoTemu Logo'})
    assert logo is not None
    assert logo['src'] in ['/static/icons/logo.png', '/icons/logo.png']

    # Check for the main heading
    heading = soup.find('h1')
    assert heading is not None
    assert "Twój email został pomyślnie zweryfikowany!" in heading.text

    # Check for beta information
    beta_heading = soup.find('h2')
    assert beta_heading is not None
    assert "Aplikacja w fazie beta" in beta_heading.text

    # Check for the main content about beta access
    paragraphs = soup.find_all('p')
    beta_text_found = False
    for paragraph in paragraphs:
        if "DawnoTemu jest obecnie w fazie beta" in paragraph.text:
            beta_text_found = True
            break
    assert beta_text_found, "Beta access message not found in page content" 