from flask import request, jsonify, Response, redirect
from routes import audio_bp
from controllers.audio_controller import AudioController

@audio_bp.route('/audio/<string:voice_id>/<int:story_id>.mp3')
def get_audio(voice_id, story_id):
    """API endpoint to get audio file"""
    # Check if client requested a redirect to a presigned URL
    use_presigned = request.args.get('presigned', 'true').lower() == 'true'
    
    if use_presigned:
        # Get a presigned URL instead of streaming the file
        success, result, status_code = AudioController.get_audio_presigned_url(voice_id, story_id)
        
        if not success:
            return jsonify(result), status_code
            
        # Redirect the client to the presigned URL
        return redirect(result['url'])
    else:
        # Original proxy method - kept for backwards compatibility
        # Get the client's Range header (if any)
        range_header = request.headers.get('Range')
        
        success, data, status_code, extra = AudioController.get_audio(voice_id, story_id, range_header)
        
        if not success:
            return jsonify(data), status_code
        
        # Create response with audio data
        response = Response(data, status=status_code, mimetype='audio/mpeg')
        response.headers['Accept-Ranges'] = 'bytes'
        
        # If a ContentRange header was returned, include it in the response
        if extra and 'content_range' in extra and extra['content_range']:
            response.headers['Content-Range'] = extra['content_range']
            
        # Add Content-Length header
        if extra and 'content_length' in extra:
            response.headers['Content-Length'] = str(extra['content_length'])
            
        # Add Content-Disposition header
        response.headers['Content-Disposition'] = f'attachment; filename={story_id}.mp3'
        
        return response

@audio_bp.route('/audio/url/<string:voice_id>/<int:story_id>')
def get_audio_url(voice_id, story_id):
    """API endpoint to get a presigned URL for direct S3 access"""
    # Get expiration time from query params (default: 1 hour)
    expires_in = int(request.args.get('expires', 3600))
    
    success, result, status_code = AudioController.get_audio_presigned_url(
        voice_id, 
        story_id,
        expires_in=expires_in
    )
    
    return jsonify(result), status_code

# Keep existing routes
@audio_bp.route('/audio/exists/<string:voice_id>/<int:story_id>')
def check_audio_exists(voice_id, story_id):
    """API endpoint to check if audio exists"""
    success, result, status_code = AudioController.check_audio_exists(voice_id, story_id)
    
    return jsonify(result), status_code

@audio_bp.route('/synthesize', methods=['POST'])
def synthesize_speech():
    """API endpoint to synthesize speech"""
    data = request.json
    
    # Validate request data
    if not (voice_id := data.get('voice_id')):
        return jsonify({"error": "Missing voice_id"}), 400
        
    if not (story_id := data.get('story_id')):
        return jsonify({"error": "Missing story_id"}), 400
    
    success, result, status_code = AudioController.synthesize_audio(voice_id, story_id)
    
    return jsonify(result), status_code