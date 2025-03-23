# app.py
from flask import Flask
import os
from config import Config
from routes import register_blueprints
from flask_cors import CORS
from database import init_db
from admin import init_admin
from admin import init_admin
from utils.s3_client import S3Client
from utils.email_service import EmailService

is_development = os.getenv('FLASK_ENV', 'production').lower() == 'development' or \
                 os.getenv('FLASK_DEBUG', 'False').lower() == 'true'

# Validate configuration
Config.validate()

# Initialize Flask app
app = Flask(__name__, static_folder='static', static_url_path='/')

# Configure the app
app.config['SQLALCHEMY_DATABASE_URI'] = Config.SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = Config.SQLALCHEMY_TRACK_MODIFICATIONS
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USE_SSL'] = os.getenv('MAIL_USE_SSL', 'False').lower() == 'true'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', 'noreply@storyvoice.app')
app.config['FRONTEND_URL'] = os.getenv('FRONTEND_URL', 'http://localhost:3000')

# Set secret key for session management
app.secret_key = os.getenv('SECRET_KEY')

# Initialize S3 client early - single initialization for entire application
try:
    S3Client.initialize()
    app.logger.info("S3 client initialized successfully at app startup")
except Exception as e:
    app.logger.error(f"Failed to initialize S3 client: {str(e)}")

# Initialize database
init_db(app)
init_admin(app)
EmailService.init_app(app)

if is_development:
    # In development mode, allow all origins
    CORS(app)
    print("CORS configured for development: allowing all origins")
else:
    # In production, restrict CORS to allowed origins.
    # The regex below matches any HTTPS subdomain of dawnotemu.app
    allowed_origins = [
        r"^https:\/\/(?:[a-z0-9-]+\.)?dawnotemu\.app$",  # Matches e.g. https://www.dawnotemu.app or https://api.dawnotemu.app
    ]
    CORS(app, origins=allowed_origins)
    print("CORS configured for production with allowed origins:", allowed_origins)

# Register blueprints
register_blueprints(app)

if __name__ == '__main__':
    app.run(
        host=os.getenv('HOST', '0.0.0.0'),
        port=int(os.getenv('PORT', 8000)),
        debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    )