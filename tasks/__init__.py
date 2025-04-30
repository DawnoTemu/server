"""
Celery task queue configuration for StoryVoice async processing.
This module sets up the Celery instance for handling background tasks.
"""

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
    worker_prefetch_multiplier=1,  # One task per worker at a time (to avoid memory issues)
    task_acks_late=True,  # Acknowledge tasks after execution (not before)
)

# This will be set in app.py
flask_app = None

# Import task modules to register with Celery
from tasks import voice_tasks, audio_tasks