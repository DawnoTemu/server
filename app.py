from flask import Flask
import os
from config import Config
from routes import register_blueprints
from flask_cors import CORS

is_development = os.getenv('FLASK_ENV', 'production').lower() == 'development' or \
                 os.getenv('FLASK_DEBUG', 'False').lower() == 'true'

# Validate configuration
Config.validate()

# Initialize Flask app
app = Flask(__name__, static_folder='static', static_url_path='/')

if is_development:
    # In development mode, allow all origins
    CORS(app)
    print("CORS configured for development: allowing all origins")

# Register blueprints
register_blueprints(app)

if __name__ == '__main__':
    app.run(
        host=os.getenv('HOST', '0.0.0.0'),
        port=int(os.getenv('PORT', 8000)),
        debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    )