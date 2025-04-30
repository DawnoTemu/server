import os
from celery import Celery
import logging

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