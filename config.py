import os
from pathlib import Path
from dotenv import load_dotenv
from utils.s3_client import S3Client

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
    
    # ElevenLabs API configuration
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
    
    # File paths and storage
    UPLOAD_FOLDER = Path("uploads")
    STORIES_DIR = Path("stories")
    
    # Voice configuration
    ALLOWED_EXTENSIONS = {"wav", "mp3"}
    VOICE_NAME = "MyClonedVoice"
    
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