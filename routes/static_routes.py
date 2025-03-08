from flask import send_from_directory
from routes import static_bp

@static_bp.route('/')
def index():
    """Serve the main application page"""
    return send_from_directory('static', 'app.html')

@static_bp.route('/manifest.json')
def serve_manifest():
    """Serve the PWA manifest file"""
    return send_from_directory('static', 'manifest.json')

@static_bp.route('/sw.js')
def serve_sw():
    """Serve the service worker with cache control headers"""
    response = send_from_directory('static', 'sw.js')
    response.headers['Cache-Control'] = 'no-cache, max-age=0'
    return response

@static_bp.route('/<path:filename>')
def serve_static(filename):
    """Serve static files (CSS, JS, images, etc.)"""
    if '.' in filename:
        ext = filename.rsplit('.', 1)[1].lower()
        if ext in {'css', 'js', 'html', 'png', 'jpg', 'jpeg', 'gif', 'ico', 'svg'}:
            return send_from_directory('static', filename)
    return "Not Found", 404