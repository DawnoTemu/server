#!/usr/bin/env python
"""
Celery worker entrypoint for StoryVoice async processing.
This script initializes and runs the Celery worker.

Usage:
    celery -A celery_worker.celery_app worker --loglevel=info
"""

import os
import logging
import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from app import app
from tasks import celery_app
from config import Config

# Initialize Sentry SDK for Celery worker
if Config.SENTRY_DSN:
    sentry_sdk.init(
        dsn=Config.SENTRY_DSN,
        # Add data like request headers and IP for users,
        # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
        send_default_pii=True,
        # Set traces sample rate to 1.0 to capture 100% of transactions for performance monitoring
        # We recommend adjusting this value in production
        traces_sample_rate=1.0,
        # Enable Celery integration
        integrations=[CeleryIntegration()],
    )
    logging.info("Sentry SDK initialized successfully for Celery worker")
else:
    logging.warning("SENTRY_DSN not found in environment variables. Sentry monitoring is disabled for Celery worker.")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

if __name__ == '__main__':
    # This is just for running via 'python celery_worker.py'
    # Normally you would use the celery command line as shown above
    celery_app.start()
    