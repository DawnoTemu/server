#!/usr/bin/env python
"""
Celery worker entrypoint for StoryVoice async processing.
This script initializes and runs the Celery worker.

Usage:
    celery -A celery_worker.celery_app worker --loglevel=info
"""

import os
import logging
from app import app
from tasks import celery_app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

if __name__ == '__main__':
    # This is just for running via 'python celery_worker.py'
    # Normally you would use the celery command line as shown above
    celery_app.start()
    