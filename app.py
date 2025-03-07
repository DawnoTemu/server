from flask import Flask, request, jsonify, send_from_directory, Response
import uuid
import os
import requests
from dotenv import load_dotenv
from io import BytesIO
import json
from pathlib import Path
import boto3
from botocore.exceptions import ClientError

# Load environment variables
load_dotenv()

# Configuration
CONFIG = {
    "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID"),
    "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY"),
    "AWS_REGION": os.getenv("AWS_REGION"),
    "S3_BUCKET": os.getenv("S3_BUCKET_NAME"),
    "API_KEY": os.getenv("ELEVENLABS_API_KEY"),
    "UPLOAD_FOLDER": Path("uploads"),
    "STORIES_DIR": Path("stories"),
    "ALLOWED_EXTENSIONS": {"wav", "mp3"},
    "VOICE_NAME": "MyClonedVoice"
}

# Validate configuration
missing = [k for k, v in CONFIG.items() if v is None and k != "VOICE_NAME"]
if missing:
    raise EnvironmentError(f"Missing environment variables: {', '.join(missing)}")

# Create necessary directories
CONFIG["UPLOAD_FOLDER"].mkdir(parents=True, exist_ok=True)
CONFIG["STORIES_DIR"].mkdir(parents=True, exist_ok=True)

# Initialize AWS S3 client
s3 = boto3.client(
    's3',
    aws_access_key_id=CONFIG["AWS_ACCESS_KEY_ID"],
    aws_secret_access_key=CONFIG["AWS_SECRET_ACCESS_KEY"],
    region_name=CONFIG["AWS_REGION"]
)

# Initialize requests session for ElevenLabs API
api_session = requests.Session()
api_session.headers.update({"xi-api-key": CONFIG["API_KEY"]})

# Initialize Flask app
app = Flask(__name__, static_folder='static', static_url_path='/')

# Helper functions
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in CONFIG["ALLOWED_EXTENSIONS"]

def get_mime_type(filename):
    return 'audio/wav' if filename.lower().endswith('.wav') else 'audio/mpeg'

def delete_s3_prefix(prefix):
    paginator = s3.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=CONFIG["S3_BUCKET"], Prefix=prefix):
        if 'Contents' in page:
            delete_keys = [{'Key': obj['Key']} for obj in page['Contents']]
            s3.delete_objects(
                Bucket=CONFIG["S3_BUCKET"],
                Delete={'Objects': delete_keys}
            )

# Routes
@app.route('/')
def index():
    return send_from_directory('static', 'app.html')

@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory('static', 'manifest.json')

@app.route('/sw.js')
def serve_sw():
    response = send_from_directory('static', 'sw.js')
    response.headers['Cache-Control'] = 'no-cache, max-age=0'
    return response

@app.route('/<path:filename>')
def serve_static(filename):
    if '.' in filename:
        ext = filename.rsplit('.', 1)[1].lower()
        if ext in {'css', 'js', 'html', 'png', 'jpg', 'jpeg', 'gif', 'ico', 'svg'}:
            return send_from_directory('static', filename)
    return "Not Found", 404

@app.route('/api/clone', methods=['POST'])
def clone_voice():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({"error": "Empty filename"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "Invalid file type"}), 400

    try:
        # Use in-memory file processing
        filename = f"clone_{uuid.uuid4().hex}_{file.filename}"
        files = {
            "files": (filename, file.stream, get_mime_type(file.filename)),
            "name": (None, CONFIG["VOICE_NAME"]),
            "description": (None, "Cloned voice from user upload"),
        }

        response = api_session.post(
            "https://api.elevenlabs.io/v1/voices/add",
            files=files
        )

        if response.status_code == 200:
            return jsonify({
                "voice_id": response.json()["voice_id"],
                "name": CONFIG["VOICE_NAME"]
            }), 200
        return jsonify({"error": response.json().get("detail", "Cloning failed")}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/voices/<string:voice_id>', methods=['DELETE'])
def delete_voice(voice_id):
    try:
        response = api_session.delete(
            f"https://api.elevenlabs.io/v1/voices/{voice_id}"
        )
        if response.status_code != 200:
            return jsonify({
                "error": "Failed to delete voice",
                "details": response.json().get("detail", "Unknown error")
            }), 500

        delete_s3_prefix(f"{voice_id}/")
        return jsonify({"message": "Voice and associated files deleted"}), 200

    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"API communication failed: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/stories')
def list_stories():
    try:
        stories = []
        for file in CONFIG["STORIES_DIR"].glob('*.json'):
            if file.name == 'index.json':
                continue
            with open(file, 'r', encoding='utf-8') as f:
                story_data = json.load(f)
                stories.append({
                    'id': story_data.get('id'),
                    'title': story_data.get('title'),
                    'author': story_data.get('author')
                })
        return jsonify(stories), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/stories/<int:story_id>')
def get_story(story_id):
    """Get specific story content"""
    try:
        # Convert Path object to string for Flask compatibility
        stories_dir = str(CONFIG["STORIES_DIR"])
        return send_from_directory(
            stories_dir,
            f'{story_id}.json',
            mimetype='application/json'
        )
    except FileNotFoundError:
        return jsonify({"error": "Story not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/audio/<string:voice_id>/<int:story_id>.mp3')
def get_audio(voice_id, story_id):
    s3_key = f"{voice_id}/{story_id}.mp3"
    # Get the client's Range header (if any)
    range_header = request.headers.get('Range')
    s3_kwargs = {'Bucket': CONFIG["S3_BUCKET"], 'Key': s3_key}
    if range_header:
        s3_kwargs['Range'] = range_header

    try:
        s3_response = s3.get_object(**s3_kwargs)
    except ClientError as e:
        return jsonify({"error": str(e)}), 404

    data = s3_response['Body'].read()
    # If a Range was requested, S3 returns status 206 (Partial Content)
    status_code = 206 if range_header else 200

    response = Response(data, status=status_code, mimetype='audio/mpeg')
    response.headers['Accept-Ranges'] = 'bytes'
    # If S3 returned a ContentRange header (when a Range was requested), include it in the response.
    if range_header and 'ContentRange' in s3_response:
        response.headers['Content-Range'] = s3_response['ContentRange']
    response.headers['Content-Length'] = s3_response['ContentLength']
    response.headers['Content-Disposition'] = f'attachment; filename={story_id}.mp3'
    return response


@app.route('/api/audio/exists/<string:voice_id>/<int:story_id>')
def check_audio_exists(voice_id, story_id):
    try:
        s3.head_object(Bucket=CONFIG["S3_BUCKET"], Key=f"{voice_id}/{story_id}.mp3")
        return jsonify({"exists": True}), 200
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            return jsonify({"exists": False}), 200
        return jsonify({"error": str(e)}), 500

@app.route('/api/synthesize', methods=['POST'])
def synthesize_speech():
    try:
        data = request.json
        if not (voice_id := data.get('voice_id')):
            return jsonify({"error": "Missing voice_id"}), 400
        if not (story_id := data.get('story_id')):
            return jsonify({"error": "Missing story_id"}), 400
        
        # Load the story text from the JSON file in the stories directory.
        story_file = CONFIG["STORIES_DIR"] / f"{story_id}.json"
        if not story_file.exists():
            return jsonify({"error": "Story file not found"}), 404
        
        with story_file.open('r', encoding='utf-8') as f:
            story_data = json.load(f)
        
        text = story_data.get("content")
        if not text:
            return jsonify({"error": "Story text not found in file"}), 400

        response = api_session.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream",
            json={
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.45,
                    "similarity_boost": 0.85,
                    "style": 0.35,
                    "use_speaker_boost": True,
                    "speed": 1.2
                }
            },
            headers={"Accept": "audio/mpeg"}
        )
        response.raise_for_status()

        s3_key = f"{voice_id}/{story_id}.mp3"
        s3.upload_fileobj(
            BytesIO(response.content),
            CONFIG["S3_BUCKET"],
            s3_key,
            ExtraArgs={'ContentType': 'audio/mpeg'}
        )

        return jsonify({
            "status": "success",
            "url": s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': CONFIG["S3_BUCKET"], 'Key': s3_key},
                ExpiresIn=3600
            )
        }), 200

    except requests.exceptions.HTTPError as e:
        return jsonify({"error": str(e.response.json())}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host=os.getenv('HOST', '0.0.0.0'), 
            port=int(os.getenv('PORT', 8000)))