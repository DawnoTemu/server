import io
import os
import math
import logging

# Configure logger
logger = logging.getLogger('audio_splitter')

def split_audio_file(file_data, filename, max_size_mb=9.5):
    """
    Split a file into chunks smaller than the specified maximum size
    This is a simplified version that doesn't require audio processing libraries.
    
    Args:
        file_data: File-like object containing file data
        filename: Original filename
        max_size_mb: Maximum size of each chunk in MB (default: 9.5MB to be safe)
        
    Returns:
        list: List of (chunk_filename, chunk_file_data, mime_type) tuples
    """
    try:
        # Determine mime type from filename
        file_ext = os.path.splitext(filename)[1].lower()
        mime_type = "audio/wav" if file_ext == '.wav' else "audio/mpeg"
        
        # Convert max size to bytes (with some margin for safety)
        max_size_bytes = int(max_size_mb * 1024 * 1024)
        
        # Read the file data
        file_data.seek(0)
        file_content = file_data.read()
        file_size = len(file_content)
        
        # If file is already smaller than max size, return it as is
        if file_size <= max_size_bytes:
            file_data.seek(0)  # Reset position for later use
            logger.info(f"File {filename} is already under size limit ({file_size/1024/1024:.2f}MB)")
            return [(filename, file_data, mime_type)]
        
        logger.info(f"Splitting file {filename} of size {file_size/1024/1024:.2f}MB into chunks")
        
        # Calculate number of chunks needed - using max_size_bytes directly
        num_chunks = math.ceil(file_size / max_size_bytes)
        logger.info(f"Will create {num_chunks} chunks of up to {max_size_mb:.2f}MB each")
        
        # Generate chunks - each chunk will be maximum possible size
        chunks = []
        for i in range(0, file_size, max_size_bytes):
            # Get chunk data
            end = min(i + max_size_bytes, file_size)
            chunk_data = file_content[i:end]
            
            # Create a filename for this chunk
            chunk_index = i // max_size_bytes
            basename = os.path.splitext(os.path.basename(filename))[0]
            chunk_filename = f"{basename}_chunk{chunk_index+1}{file_ext}"
            
            # Convert to file-like object
            chunk_file = io.BytesIO(chunk_data)
            
            # Log chunk info
            chunk_size_mb = len(chunk_data) / 1024 / 1024
            logger.info(f"Chunk {chunk_index+1}/{num_chunks}: {chunk_filename}, {chunk_size_mb:.2f}MB")
            
            chunks.append((chunk_filename, chunk_file, mime_type))
        
        return chunks
    
    except Exception as e:
        logger.error(f"Error splitting file: {str(e)}")
        # If something goes wrong, try to return the original file
        file_data.seek(0)
        return [(filename, file_data, mime_type)]