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

    Flask-SQLAlchemy's teardown_appcontext normally handles this for HTTP
    requests, but Celery tasks that exit abnormally (OOM, SIGKILL, unhandled
    exception before context exit) can leak sessions.  This signal fires
    reliably after every task execution regardless of outcome.
    """
    db.session.remove()


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