import os
from pathlib import Path
from dotenv import load_dotenv
import boto3

# Load environment variables
load_dotenv()

# Configuration class
class Config:
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
                  not callable(v)]
        if missing:
            raise EnvironmentError(f"Missing environment variables: {', '.join(missing)}")
        return True
    
    # Initialize AWS S3 client
    @classmethod
    def get_s3_client(cls):
        return boto3.client(
            's3',
            aws_access_key_id=cls.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=cls.AWS_SECRET_ACCESS_KEY,
            region_name=cls.AWS_REGION
        )