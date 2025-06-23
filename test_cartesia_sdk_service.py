#!/usr/bin/env python
import sys
import os
from dotenv import load_dotenv
import time
from io import BytesIO

# Ensure we're in the correct directory for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables from .env file
load_dotenv()

from utils.cartesia_sdk_service import CartesiaSDKService
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    # Voice ID and name from the user's request
    voice_id = "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"
    voice_name = "Jacqueline"
    
    # Short text for synthesis
    text = "This is a test of the updated CartesiaSDKService with the correct output format."
    
    print(f"Testing CartesiaSDKService speech synthesis with voice '{voice_name}'")
    
    try:
        # Use the updated CartesiaSDKService
        success, result = CartesiaSDKService.synthesize_speech(
            cartesia_voice_id=voice_id,
            text=text,
            model_id="sonic-2",
            language="en",
            speed="normal"
        )
        
        if success:
            # Save the audio to a file
            timestamp = int(time.time())
            output_filename = f"sdk_voice_synthesis_{voice_name}_{timestamp}.mp3"
            
            print(f"Writing {len(result.getvalue())} bytes to {output_filename}...")
            with open(output_filename, 'wb') as f:
                f.write(result.getvalue())
            
            print(f"✅ Speech synthesis successful!")
            print(f"✅ Audio saved to: {output_filename}")
        else:
            print(f"❌ Speech synthesis failed: {result}")
    
    except Exception as e:
        print(f"❌ Exception occurred: {str(e)}")
        print("Make sure your Cartesia API key is correct and has sufficient credits.")

if __name__ == "__main__":
    main() 