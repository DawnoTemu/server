from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import logging

# Configure logger
logger = logging.getLogger('database')

# Initialize SQLAlchemy with no app object (it will be registered later)
db = SQLAlchemy()
migrate = Migrate()

def init_db(app):
    """Initialize database with the Flask app"""
    try:
        # Initialize SQLAlchemy with the app
        db.init_app(app)
        
        # Initialize Flask-Migrate
        migrate.init_app(app, db)
        
        # Log database connection information (only in debug mode)
        if app.debug:
            logger.info(f"Database initialized with URI: {app.config['SQLALCHEMY_DATABASE_URI']}")
            
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