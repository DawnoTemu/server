import os
import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from celery import Celery
import logging
from config import Config

# Initialize Sentry SDK for Celery tasks
if Config.SENTRY_DSN:
    sentry_sdk.init(
        dsn=Config.SENTRY_DSN,
        send_default_pii=True,
        traces_sample_rate=1.0,
        integrations=[CeleryIntegration()],
    )
    logging.info("Sentry SDK initialized successfully for Celery tasks")
else:
    logging.warning("SENTRY_DSN not found in environment variables. Sentry monitoring is disabled for Celery tasks.")

# Configure logger
logger = logging.getLogger('celery_tasks')

# Create Celery instance
celery_app = Celery(
    'storyvoice',
    broker=os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
    backend=os.getenv('REDIS_URL', 'redis://localhost:6379/0')
)

# Configure Celery
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,  # 10 minutes
    task_soft_time_limit=480,  # 8 minutes
    worker_prefetch_multiplier=1,  # One task per worker at a time
    task_acks_late=True,  # Acknowledge tasks after execution
)

# This will be set in app.py
flask_app = None

def init_app(app):
    """Initialize Celery with Flask app for task context"""
    global flask_app
    flask_app = app
    
    # Update Celery config from Flask app config
    # Convert Flask-style config keys to Celery-style keys
    celery_config = {
        key: value for key, value in app.config.items()
        if key.startswith('broker_') or 
           key.startswith('result_') or 
           key.startswith('task_') or 
           key.startswith('worker_') or
           key in ['accept_content', 'enable_utc']
    }
    
    celery_app.conf.update(celery_config)
    
    class ContextTask(celery_app.Task):
        """Task that executes in a Flask application context"""
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    
    # Use ContextTask as default base for all tasks
    celery_app.Task = ContextTask
    
    return celery_app

# Import task modules to register with Celery
# Keep these imports at the bottom to avoid circular import issues
from tasks import voice_tasks, audio_tasks