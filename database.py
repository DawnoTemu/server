from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from celery.signals import task_postrun
import logging

# Configure logger
logger = logging.getLogger('database')

# Initialize SQLAlchemy with no app object (it will be registered later)
db = SQLAlchemy()
migrate = Migrate()


@task_postrun.connect
def cleanup_session_after_task(sender=None, **kwargs):
    """Remove scoped session after every Celery task to return connections to the pool.

    Flask-SQLAlchemy's teardown_appcontext normally handles session cleanup for
    HTTP requests, but Celery workers reuse a long-lived app context across
    tasks.  Without explicit cleanup, a session opened by one task can hold a
    connection through subsequent tasks, eventually exhausting the pool.
    task_postrun fires after every task completion (success or exception).
    """
    try:
        db.session.remove()
    except Exception as exc:
        logger.warning(
            "Failed to remove DB session in task_postrun (sender=%s): %s",
            getattr(sender, 'name', sender),
            exc,
        )


def init_db(app):
    """Initialize database with the Flask app"""
    try:
        # Initialize SQLAlchemy with the app
        db.init_app(app)

        # Initialize Flask-Migrate
        migrate.init_app(app, db)

        # Log database connection information (only in debug mode)
        if app.debug:
            # Extract dialect information from the URI
            uri = app.config['SQLALCHEMY_DATABASE_URI']
            dialect = uri.split('://')[0] if '://' in uri else 'unknown'
            logger.info(f"Using database dialect: {dialect}")

            # Log connection pool configuration
            if 'SQLALCHEMY_ENGINE_OPTIONS' in app.config:
                pool_options = app.config['SQLALCHEMY_ENGINE_OPTIONS']
                logger.info(f"Connection pool configured with: {pool_options}")

        return True
    except Exception as e:
        logger.error(f"Database initialization error: {str(e)}")
        raise