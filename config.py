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

_config_logger = logging.getLogger(__name__)



def _safe_positive_int_env(env_var, default):
    """Return a positive integer from an env var, falling back to *default* on bad input."""
    raw = os.getenv(env_var)
    if raw is None:
        return default
    try:
        val = int(raw)
    except (ValueError, TypeError):
        _config_logger.warning("Invalid %s=%r; falling back to %s", env_var, raw, default)
        return default
    if val <= 0:
        _config_logger.warning("%s must be > 0 (got %s); falling back to %s", env_var, val, default)
        return default
    return val


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
        "pool_pre_ping": True,
        "pool_size": _safe_positive_int_env("SQLALCHEMY_POOL_SIZE", 5),
        "max_overflow": _safe_positive_int_env("SQLALCHEMY_MAX_OVERFLOW", 5),
        "pool_recycle": 300,       # Seconds before recycling a connection
        "pool_timeout": 20,        # Seconds to wait for a connection before raising TimeoutError
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
    ELEVENLABS_MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID", "eleven_flash_v2_5")
    ELEVENLABS_SLOT_LIMIT = int(os.getenv("ELEVENLABS_SLOT_LIMIT", "30") or 0)
    # Concurrent synthesis API calls (separate from slot limit - ElevenLabs typically allows 5)
    ELEVENLABS_SYNTHESIS_CONCURRENCY = int(os.getenv("ELEVENLABS_SYNTHESIS_CONCURRENCY", "5") or 5)
    VOICE_WARM_HOLD_SECONDS = int(os.getenv("VOICE_WARM_HOLD_SECONDS", "900") or 0)
    VOICE_QUEUE_POLL_INTERVAL = int(os.getenv("VOICE_QUEUE_POLL_INTERVAL", "60") or 0)
    # Proactive cleanup: evict voices idle longer than this even when queue is empty (0 = disabled)
    VOICE_MAX_IDLE_HOURS = int(os.getenv("VOICE_MAX_IDLE_HOURS", "24") or 0)

    # Credits configuration (tolerant to invalid env input)
    CREDITS_UNIT_LABEL = os.getenv("CREDITS_UNIT_LABEL", "Story Points (Punkty Magii)")
    try:
        _cus_raw = os.getenv("CREDITS_UNIT_SIZE", "1000")
        _cus_val = int(_cus_raw) if str(_cus_raw).strip() != "" else 1000
    except Exception:
        _cus_val = 1000
        logging.getLogger(__name__).warning("Invalid CREDITS_UNIT_SIZE=%r, using default 1000", os.getenv("CREDITS_UNIT_SIZE"))
    CREDITS_UNIT_SIZE = _cus_val if _cus_val > 0 else 1000
    try:
        _ic_raw = os.getenv("INITIAL_CREDITS", "10")
        _ic_val = int(_ic_raw) if str(_ic_raw).strip() != "" else 10
    except Exception:
        _ic_val = 10
    INITIAL_CREDITS = _ic_val if _ic_val >= 0 else 10

    # Subscription gate feature flag.
    #
    # When False (default), the audio synthesis gate in audio_controller is
    # bypassed and old mobile clients that cannot handle the
    # `SUBSCRIPTION_REQUIRED` error code keep working. Subscription data
    # (trial_expires_at, subscription_active, webhooks, addon grants, etc.)
    # is still recorded correctly; only enforcement is disabled.
    #
    # Flip to True only after >=95% of active users are on a mobile build
    # that handles the gate. See SUBSCRIPTION_MOBILE_REQUIREMENTS.md for the
    # flip-day runbook (includes a trial-refresh SQL to reset stale trial
    # windows for users who signed up during the flag-off period).
    ENFORCE_SUBSCRIPTION_GATE = (
        os.getenv("ENFORCE_SUBSCRIPTION_GATE", "false").strip().lower()
        in ("1", "true", "yes", "on")
    )

    # RevenueCat / Subscription
    REVENUECAT_WEBHOOK_SECRET = os.getenv("REVENUECAT_WEBHOOK_SECRET")
    REVENUECAT_API_KEY = os.getenv("REVENUECAT_API_KEY")
    REVENUECAT_PROJECT_ID = os.getenv("REVENUECAT_PROJECT_ID")
    YEARLY_PRODUCT_IDS = frozenset(
        s.strip() for s in os.getenv("YEARLY_PRODUCT_IDS", "dawnotemu_annual,dawnotemu_yearly").split(",") if s.strip()
    )
    try:
        _td_raw = os.getenv("TRIAL_DURATION_DAYS", "14")
        _td_val = int(_td_raw) if str(_td_raw).strip() != "" else 14
    except Exception:
        _td_val = 14
        logging.getLogger(__name__).warning("Invalid TRIAL_DURATION_DAYS=%r, using default 14", os.getenv("TRIAL_DURATION_DAYS"))
    TRIAL_DURATION_DAYS = _td_val if _td_val > 0 else 14
    try:
        _msc_raw = os.getenv("MONTHLY_SUBSCRIPTION_CREDITS", "26")
        _msc_val = int(_msc_raw) if str(_msc_raw).strip() != "" else 26
    except Exception:
        _msc_val = 26
        logging.getLogger(__name__).warning("Invalid MONTHLY_SUBSCRIPTION_CREDITS=%r, using default 26", os.getenv("MONTHLY_SUBSCRIPTION_CREDITS"))
    MONTHLY_SUBSCRIPTION_CREDITS = _msc_val if _msc_val > 0 else 26
    try:
        _ysc_raw = os.getenv("YEARLY_SUBSCRIPTION_MONTHLY_CREDITS", "30")
        _ysc_val = int(_ysc_raw) if str(_ysc_raw).strip() != "" else 30
    except Exception:
        _ysc_val = 30
        logging.getLogger(__name__).warning("Invalid YEARLY_SUBSCRIPTION_MONTHLY_CREDITS=%r, using default 30", os.getenv("YEARLY_SUBSCRIPTION_MONTHLY_CREDITS"))
    YEARLY_SUBSCRIPTION_MONTHLY_CREDITS = _ysc_val if _ysc_val > 0 else 30

    # Consumption priority: event -> monthly -> referral -> add_on -> free
    _csp_raw = os.getenv("CREDIT_SOURCES_PRIORITY", "event,monthly,referral,add_on,free")
    CREDIT_SOURCES_PRIORITY = [s.strip() for s in _csp_raw.split(',') if s.strip()]
    # Default monthly grant amount (0 disables scheduler grants)
    try:
        _mc_raw = os.getenv("MONTHLY_CREDITS_DEFAULT", "0")
        _mc_val = int(_mc_raw) if str(_mc_raw).strip() != "" else 0
    except Exception:
        _mc_val = 0
        logging.getLogger(__name__).warning("Invalid MONTHLY_CREDITS_DEFAULT=%r, using default 0", os.getenv("MONTHLY_CREDITS_DEFAULT"))
    MONTHLY_CREDITS_DEFAULT = _mc_val if _mc_val >= 0 else 0
    
    # Create required directories
    UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    STORIES_DIR.mkdir(parents=True, exist_ok=True)
    
    # Validate configuration
    @classmethod
    def validate(cls):
        _optional = {"VOICE_NAME", "DATABASE_URL", "REVENUECAT_WEBHOOK_SECRET", "REVENUECAT_API_KEY", "REVENUECAT_PROJECT_ID"}
        missing = [k for k, v in cls.__dict__.items()
                  if not k.startswith('__') and
                  v is None and
                  k not in _optional and
                  not callable(v)]
        if missing:
            raise EnvironmentError(f"Missing environment variables: {', '.join(missing)}")

        # Warn about subscription config gaps that would silently break features
        _subscription_vars = {
            "REVENUECAT_WEBHOOK_SECRET": cls.REVENUECAT_WEBHOOK_SECRET,
            "REVENUECAT_API_KEY": cls.REVENUECAT_API_KEY,
            "REVENUECAT_PROJECT_ID": cls.REVENUECAT_PROJECT_ID,
        }
        missing_sub = [k for k, v in _subscription_vars.items() if not v]
        if missing_sub:
            _config_logger.warning(
                "Subscription features partially configured — missing: %s. "
                "Webhook auth and addon receipt validation will fail.",
                ", ".join(missing_sub),
            )

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
