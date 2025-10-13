import os
import boto3
import logging
from pathlib import Path
from dotenv import load_dotenv
from utils.s3_client import S3Client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Silence overly verbose loggers
logging.getLogger('boto3').setLevel(logging.WARNING)
logging.getLogger('botocore').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('werkzeug').setLevel(logging.WARNING)

# Load environment variables
load_dotenv()

# Configuration class
class Config:
    # Database configuration
    DATABASE_URL = os.getenv("DATABASE_URL")
    
    # If DATABASE_URL is provided, use it; otherwise use default
    # Use postgresql+psycopg for psycopg3 (instead of postgresql+psycopg2)
    if DATABASE_URL and not DATABASE_URL.startswith('postgresql+psycopg://'):
        # If it starts with postgresql:// or postgres://, replace with postgresql+psycopg://
        if DATABASE_URL.startswith(('postgresql://', 'postgres://')):
            # Handle potential Heroku style URLs
            if DATABASE_URL.startswith('postgres://'):
                DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
            # Add +psycopg dialect
            DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+psycopg://', 1)
    
    SQLALCHEMY_DATABASE_URI = DATABASE_URL if DATABASE_URL else "postgresql+psycopg://postgres:postgres@localhost:5432/storyvoice"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Additional psycopg3 specific configuration
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,  # Verify connections before using them
        "pool_size": 5,         # Max number of connections in the pool
        "max_overflow": 10,     # Max number of connections that can be created beyond pool_size
    }
    
    # AWS and S3 configuration
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_REGION = os.getenv("AWS_REGION")
    S3_BUCKET = os.getenv("S3_BUCKET_NAME")
    S3_REQUIRE_SSE = os.getenv("AWS_S3_USE_SSE", "true").lower() not in ("0", "false", "no")
    
    # ElevenLabs API configuration
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
    CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY")
    
    # Resend API configuration
    RESEND_API_KEY = os.getenv("RESEND_API_KEY")
    RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "no-reply@dawnotemu.app")
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
    BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
    
    # Sentry configuration
    SENTRY_DSN = os.getenv("SENTRY_DSN")
    
    # Voice service selection ("elevenlabs" or "cartesia")
    PREFERRED_VOICE_SERVICE = os.getenv("PREFERRED_VOICE_SERVICE", "elevenlabs").lower()
    
    # Security configuration
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    
    # Admin API Keys for production operations (comma-separated list)
    ADMIN_API_KEYS = []
    if os.getenv("ADMIN_API_KEYS"):
        ADMIN_API_KEYS = [key.strip() for key in os.getenv("ADMIN_API_KEYS").split(",")]
    
    # File paths and storage
    UPLOAD_FOLDER = Path("uploads")
    STORIES_DIR = Path("stories")
    
    # Voice configuration
    ALLOWED_EXTENSIONS = {"wav", "mp3", "m4a"}
    VOICE_NAME = "MyClonedVoice"
    ELEVENLABS_SLOT_LIMIT = int(os.getenv("ELEVENLABS_SLOT_LIMIT", "30") or 0)
    VOICE_WARM_HOLD_SECONDS = int(os.getenv("VOICE_WARM_HOLD_SECONDS", "900") or 0)
    VOICE_QUEUE_POLL_INTERVAL = int(os.getenv("VOICE_QUEUE_POLL_INTERVAL", "60") or 0)

    # Credits configuration (tolerant to invalid env input)
    CREDITS_UNIT_LABEL = os.getenv("CREDITS_UNIT_LABEL", "Story Points (Punkty Magii)")
    try:
        _cus_raw = os.getenv("CREDITS_UNIT_SIZE", "1000")
        _cus_val = int(_cus_raw) if str(_cus_raw).strip() != "" else 1000
    except Exception:
        _cus_val = 1000
    CREDITS_UNIT_SIZE = _cus_val if _cus_val > 0 else 1000
    try:
        _ic_raw = os.getenv("INITIAL_CREDITS", "10")
        _ic_val = int(_ic_raw) if str(_ic_raw).strip() != "" else 10
    except Exception:
        _ic_val = 10
    INITIAL_CREDITS = _ic_val if _ic_val >= 0 else 10
    # Consumption priority: event -> monthly -> referral -> add_on -> free
    _csp_raw = os.getenv("CREDIT_SOURCES_PRIORITY", "event,monthly,referral,add_on,free")
    CREDIT_SOURCES_PRIORITY = [s.strip() for s in _csp_raw.split(',') if s.strip()]
    # Default monthly grant amount (0 disables scheduler grants)
    try:
        _mc_raw = os.getenv("MONTHLY_CREDITS_DEFAULT", "0")
        _mc_val = int(_mc_raw) if str(_mc_raw).strip() != "" else 0
    except Exception:
        _mc_val = 0
    MONTHLY_CREDITS_DEFAULT = _mc_val if _mc_val >= 0 else 0
    
    # Create required directories
    UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    STORIES_DIR.mkdir(parents=True, exist_ok=True)
    
    # Validate configuration
    @classmethod
    def validate(cls):
        missing = [k for k, v in cls.__dict__.items() 
                  if not k.startswith('__') and 
                  v is None and 
                  k != "VOICE_NAME" and
                  k != "DATABASE_URL" and  # DATABASE_URL can be None, will use default
                  not callable(v)]
        if missing:
            raise EnvironmentError(f"Missing environment variables: {', '.join(missing)}")
        return True
    
    # Get S3 client using our optimized implementation
    @classmethod
    def get_s3_client(cls):
        """
        Get the singleton S3 client instance 
        (Maintains compatibility with existing code)
        """
        return S3Client.get_client()
    
    # Helper method to generate S3 URLs (now delegates to S3Client)
    @classmethod
    def get_s3_url(cls, key, expires_in=3600):
        """
        Generate a presigned URL for S3 object
        """
        if not key:
            return None
        return S3Client.generate_presigned_url(key, expires_in)
