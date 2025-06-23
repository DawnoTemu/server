#!/usr/bin/env python
import sys
import os
import requests
from dotenv import load_dotenv
import time
import json
from io import BytesIO

# Ensure we're in the correct directory for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables from .env file
load_dotenv()

import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    # Voice ID and name from the user's request
    voice_id = "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"
    voice_name = "Jacqueline"
    
    # Short text for synthesis (keeping it minimal for testing)
    text = "This is a test of voice synthesis with Cartesia API."
    
    print(f"Testing Cartesia speech synthesis with voice '{voice_name}'")
    
    # API base URL and version
    api_base_url = "https://api.cartesia.ai"
    api_version = "2024-11-13"
    
    # Get API key
    api_key = os.getenv("CARTESIA_API_KEY")
    if not api_key:
        print("❌ CARTESIA_API_KEY environment variable not set")
        return
    
    # According to the official documentation at:
    # https://docs.cartesia.ai/2024-11-13/api-reference/tts/bytes
    # the correct output_format needs container, bit_rate and sample_rate
    output_format = {
        "container": "mp3",
        "bit_rate": 128000,
        "sample_rate": 44100
    }
    
    # Prepare voice object as per docs (with mode: "id")
    voice = {
        "mode": "id",
        "id": voice_id
    }
    
    # Prepare headers
    headers = {
        "X-API-Key": api_key,
        "Cartesia-Version": api_version,
        "Content-Type": "application/json"
    }
    
    # Prepare request payload exactly as per the API documentation
    payload = {
        "model_id": "sonic-2",
        "transcript": text,
        "voice": voice,
        "output_format": output_format,
        "language": "en"
    }
    
    # Print the payload for debugging
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        # Make API request
        print(f"Sending request to Cartesia API...")
        response = requests.post(
            f"{api_base_url}/tts/bytes",
            headers=headers,
            json=payload
        )
        
        # Check response status
        if response.status_code == 200:
            # Save the audio to a file
            timestamp = int(time.time())
            output_filename = f"voice_synthesis_{voice_name}_{timestamp}.mp3"
            
            print(f"Writing {len(response.content)} bytes to {output_filename}...")
            with open(output_filename, 'wb') as f:
                f.write(response.content)
            
            print(f"✅ Speech synthesis successful!")
            print(f"✅ Audio saved to: {output_filename}")
        else:
            print(f"❌ API request failed with status code {response.status_code}")
            try:
                error_message = response.json().get('error', response.text)
                print(f"Error: {error_message}")
            except:
                print(f"Response: {response.text}")
    
    except Exception as e:
        print(f"❌ Exception occurred: {str(e)}")
        print("Make sure your Cartesia API key is correct and has sufficient credits.")

if __name__ == "__main__":
    main() 