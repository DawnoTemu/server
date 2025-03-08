def allowed_file(filename, allowed_extensions):
    """
    Check if a file has an allowed extension
    
    Args:
        filename: Name of the file to check
        allowed_extensions: Set of allowed extensions
        
    Returns:
        bool: True if file is allowed, False otherwise
    """
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

def get_mime_type(filename):
    """
    Get MIME type based on file extension
    
    Args:
        filename: Name of the file
        
    Returns:
        str: MIME type string
    """
    return 'audio/wav' if filename.lower().endswith('.wav') else 'audio/mpeg'