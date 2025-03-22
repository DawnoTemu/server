import io
import os
import math
import logging
import subprocess
import tempfile
from io import BytesIO

# Configure logger
logger = logging.getLogger('audio_splitter')

def convert_to_mp3(file_data, filename):
    """
    Convert audio file to MP3 format using ffmpeg
    
    Args:
        file_data: File-like object containing audio data
        filename: Original filename
        
    Returns:
        tuple: (BytesIO object with MP3 data, new filename)
    """
    try:
        # Reset file pointer to beginning
        file_data.seek(0)
        
        # Determine the input format from filename
        file_ext = os.path.splitext(filename)[1].lower()
        
        # If already MP3, return as is
        if file_ext == '.mp3':
            logger.info(f"File {filename} is already MP3, skipping conversion")
            return file_data, filename
        
        # Create temporary files for input and output
        # We need temp files for ffmpeg, but they're removed automatically
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as input_temp:
            input_temp.write(file_data.read())
            input_temp_path = input_temp.name
        
        output_temp_path = input_temp_path.replace(file_ext, '.mp3')
        
        # Create new filename
        basename = os.path.splitext(os.path.basename(filename))[0]
        new_filename = f"{basename}.mp3"
        
        try:
            # Run ffmpeg conversion
            cmd = [
                'ffmpeg',
                '-i', input_temp_path,
                '-y',  # Overwrite output file if it exists
                '-acodec', 'libmp3lame',
                '-ab', '128k',
                '-ac', '2',  # Stereo
                '-ar', '44100',  # Sample rate
                output_temp_path
            ]
            
            # Execute ffmpeg command
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE
            )
            stdout, stderr = process.communicate()
            
            if process.returncode != 0:
                logger.error(f"FFMPEG conversion error: {stderr.decode()}")
                file_data.seek(0)
                return file_data, filename
                
            # Read the converted MP3 file into a BytesIO object
            with open(output_temp_path, 'rb') as f:
                mp3_data = BytesIO(f.read())
            
            logger.info(f"Converted {filename} to MP3 format")
            return mp3_data, new_filename
            
        finally:
            # Clean up temporary files
            if os.path.exists(input_temp_path):
                os.unlink(input_temp_path)
            if os.path.exists(output_temp_path):
                os.unlink(output_temp_path)
    
    except Exception as e:
        logger.error(f"Error converting to MP3: {str(e)}")
        # Return original file if conversion fails
        file_data.seek(0)
        return file_data, filename

def split_audio_file(file_data, filename, max_size_mb=9.5):
    """
    Convert audio to MP3 if needed and split into chunks smaller than the specified maximum size
    
    Args:
        file_data: File-like object containing audio data
        filename: Original filename
        max_size_mb: Maximum size of each chunk in MB (default: 9.5MB to be safe)
        
    Returns:
        list: List of (chunk_filename, chunk_file_data, mime_type) tuples
    """
    try:
        # First convert to MP3 if needed
        mp3_data, mp3_filename = convert_to_mp3(file_data, filename)
        
        # Set correct mime type
        mime_type = "audio/mpeg"
        
        # Convert max size to bytes
        max_size_bytes = int(max_size_mb * 1024 * 1024)
        
        # Read the file data
        mp3_data.seek(0)
        file_content = mp3_data.read()
        file_size = len(file_content)
        
        # If file is already smaller than max size, return it as is
        if file_size <= max_size_bytes:
            mp3_data.seek(0)  # Reset position for later use
            logger.info(f"File {mp3_filename} is under size limit ({file_size/1024/1024:.2f}MB)")
            return [(mp3_filename, mp3_data, mime_type)]
        
        logger.info(f"Splitting file {mp3_filename} of size {file_size/1024/1024:.2f}MB into chunks")
        
        # Calculate number of chunks needed
        num_chunks = math.ceil(file_size / max_size_bytes)
        logger.info(f"Will create {num_chunks} chunks of up to {max_size_mb:.2f}MB each")
        
        # Generate chunks
        chunks = []
        for i in range(0, file_size, max_size_bytes):
            # Get chunk data
            end = min(i + max_size_bytes, file_size)
            chunk_data = file_content[i:end]
            
            # Create a filename for this chunk
            chunk_index = i // max_size_bytes
            basename = os.path.splitext(os.path.basename(mp3_filename))[0]
            chunk_filename = f"{basename}_chunk{chunk_index+1}.mp3"
            
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
        return [(filename, file_data, "audio/wav" if filename.lower().endswith('.wav') else "audio/mpeg")]