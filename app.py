# app.py
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from flask import Flask
import os
import logging
from config import Config
from routes import register_blueprints
from flask_cors import CORS
from database import init_db
from admin import init_admin  # Import only once
from utils.s3_client import S3Client
from utils.email_service import EmailService
from tasks import celery_app, init_app

# Initialize Sentry SDK before Flask app
if Config.SENTRY_DSN:
    sentry_sdk.init(
        dsn=Config.SENTRY_DSN,
        # Add data like request headers and IP for users,
        # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
        send_default_pii=True,
        # Set traces sample rate to 1.0 to capture 100% of transactions for performance monitoring
        # We recommend adjusting this value in production
        traces_sample_rate=1.0,
        # Enable Flask integration
        integrations=[FlaskIntegration()],
    )
    logging.info("Sentry SDK initialized successfully")
else:
    logging.warning("SENTRY_DSN not found in environment variables. Sentry monitoring is disabled.")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

is_development = os.getenv('FLASK_ENV', 'production').lower() == 'development' or \
                 os.getenv('FLASK_DEBUG', 'False').lower() == 'true'

def create_app(testing=False):
    """Create and configure the Flask application"""
    # Initialize Flask app
    app = Flask(__name__, static_folder='static', static_url_path='/')
    
    # Set secret key for session management
    if os.getenv('FLASK_ENV') == 'development' and not os.getenv('SECRET_KEY'):
        import secrets
        app.secret_key = secrets.token_hex(16)
        print("WARNING: Using a generated SECRET_KEY. This is OK for development but not for production.")
    else:
        secret_key = os.getenv('SECRET_KEY')
        if not secret_key:
            raise ValueError("SECRET_KEY environment variable must be set")
        app.secret_key = secret_key
    
    # Configure the app
    app.config['SQLALCHEMY_DATABASE_URI'] = Config.SQLALCHEMY_DATABASE_URI
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = Config.SQLALCHEMY_TRACK_MODIFICATIONS
    
    # Celery configuration
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    app.config['broker_url'] = redis_url
    app.config['result_backend'] = redis_url

    # Use Redis-backed beat scheduler by default to avoid ephemeral local files
    redbeat_url = redis_url
    app.config['beat_scheduler'] = os.getenv('CELERY_BEAT_SCHEDULER', 'redbeat.RedBeatScheduler')
    app.config['redbeat_redis_url'] = redbeat_url
    try:
        app.config['redbeat_lock_timeout'] = int(os.getenv('REDBEAT_LOCK_TIMEOUT', '120'))
    except ValueError:
        app.config['redbeat_lock_timeout'] = 120
    key_prefix = os.getenv('REDBEAT_KEY_PREFIX')
    if key_prefix:
        app.config['redbeat_key_prefix'] = key_prefix
    
    # Now validate configuration after app is initialized
    if not testing:
        try:
            Config.validate()
            logger.info("Configuration validated successfully")
        except Exception as e:
            logger.critical(f"Configuration validation failed: {str(e)}")
            # You can either re-raise here or handle the error differently
            raise
    
    # Initialize S3 client early but with proper error handling
    if not testing:
        try:
            S3Client.initialize()
            logger.info("S3 client initialized successfully at app startup")
        except Exception as e:
            logger.critical(f"Failed to initialize S3 client: {str(e)}")
            # Decide whether to exit or continue with limited functionality
            raise  # Exit if S3 is critical to your application
    
    # Initialize database, admin interface and email service
    try:
        init_db(app)
        if not testing:
            init_admin(app)
            EmailService.init_app(app)
    except Exception as e:
        logger.critical(f"Failed to initialize application components: {str(e)}")
        raise
    
    # Configure CORS
    if is_development:
        # In development mode, allow all origins
        CORS(app)
        logger.info("CORS configured for development: allowing all origins")
    else:
        # In production, restrict CORS to allowed origins
        allowed_origins = [
            r"^https:\/\/(?:[a-z0-9-]+\.)?dawnotemu\.app$",
        ]
        CORS(app, origins=allowed_origins)
        logger.info(f"CORS configured for production with allowed origins: {allowed_origins}")
    
    # Register blueprints
    register_blueprints(app)
    
    # Add a test route to verify Sentry installation
    @app.route("/test-sentry")
    def test_sentry():
        """Test route to verify Sentry installation"""
        1/0  # raises an error
        return "<p>This should not be reached</p>"
    
    return app

# Initialize Celery
app = create_app()
init_app(app)

# This will be used by Celery tasks
from tasks import flask_app
flask_app = app

# Main entry point
if __name__ == '__main__':
    app.run(
        host=os.getenv('HOST', '0.0.0.0'),
        port=int(os.getenv('PORT', 8000)),
        debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    )
