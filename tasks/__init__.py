import os
import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from celery import Celery, Task
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

# Beat/RedBeat hardening (must be set on celery_app.conf for Celery Beat)
# Defaults chosen to avoid RedBeat lock extension crash when beat loop interval > lock TTL.
try:
    celery_app.conf.beat_max_loop_interval = int(os.getenv('CELERY_BEAT_MAX_LOOP_INTERVAL', '60'))
except ValueError:
    celery_app.conf.beat_max_loop_interval = 60
    logger.warning("Invalid CELERY_BEAT_MAX_LOOP_INTERVAL. Falling back to 60.")

try:
    celery_app.conf.redbeat_lock_timeout = int(os.getenv('REDBEAT_LOCK_TIMEOUT', '600'))
except ValueError:
    celery_app.conf.redbeat_lock_timeout = 600
    logger.warning("Invalid REDBEAT_LOCK_TIMEOUT. Falling back to 600.")

if celery_app.conf.redbeat_lock_timeout <= celery_app.conf.beat_max_loop_interval:
    logger.warning(
        "REDBEAT_LOCK_TIMEOUT (%ss) must be > CELERY_BEAT_MAX_LOOP_INTERVAL (%ss) to avoid RedBeat lock crashes.",
        celery_app.conf.redbeat_lock_timeout,
        celery_app.conf.beat_max_loop_interval,
    )

logger.info(
    "Celery Beat config: beat_max_loop_interval=%ss redbeat_lock_timeout=%ss",
    celery_app.conf.beat_max_loop_interval,
    celery_app.conf.redbeat_lock_timeout,
)

# This will be set in app.py
flask_app = None


class FlaskTask(Task):
    """Base task that ensures execution inside a Flask application context.

    Use as ``base=FlaskTask`` for any task that touches the database, config,
    or other Flask extensions.  The Flask app reference is resolved lazily so
    the class can be defined before ``init_app()`` is called.
    """

    _flask_app = None

    @property
    def flask_app(self):
        if self._flask_app is None:
            from tasks import flask_app as _fa
            self._flask_app = _fa
        return self._flask_app

    def __call__(self, *args, **kwargs):
        with self.flask_app.app_context():
            return self.run(*args, **kwargs)

def init_app(app):
    """Initialize Celery with Flask app for task context"""
    global flask_app
    flask_app = app
    
    # Update Celery config from Flask app config
    # Convert Flask-style config keys to Celery-style keys
    allowed_prefixes = ('broker_', 'result_', 'task_', 'worker_', 'beat_', 'redbeat_')
    allowed_keys = {'accept_content', 'enable_utc', 'timezone'}
    celery_config = {
        key: value for key, value in app.config.items()
        if key.startswith(allowed_prefixes) or key in allowed_keys
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
from tasks import voice_tasks, audio_tasks, billing_tasks, account_tasks
