from flask import request, jsonify
from routes import voice_bp
from controllers.voice_controller import VoiceController

@voice_bp.route('/clone', methods=['POST'])
def clone_voice():
    """API endpoint for voice cloning"""
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
        
    file = request.files['file']
    
    success, result, status_code = VoiceController.clone_voice(file)
    
    return jsonify(result), status_code

@voice_bp.route('/voices/<string:voice_id>', methods=['DELETE'])
def delete_voice(voice_id):
    """API endpoint for voice deletion"""
    success, result, status_code = VoiceController.delete_voice(voice_id)
    
    return jsonify(result), status_code