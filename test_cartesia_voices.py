#!/usr/bin/env python
import sys
import os
from dotenv import load_dotenv

# Ensure we're in the correct directory for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables from .env file
load_dotenv()

from utils.cartesia_sdk_service import CartesiaSDKService

def main():
    print("Testing CartesiaSDKService - Listing voices...")
    
    try:
        # Get all voices from Cartesia
        success, result = CartesiaSDKService.list_voices()
        
        if success:
            voices = result
            print(f"Found {len(voices)} voices:")
            for i, voice in enumerate(voices, 1):
                print(f"{i}. ID: {voice.id}, Name: {voice.name}")
                
            if not voices:
                print("No voices found in your Cartesia account.")
        else:
            print(f"Error listing voices: {result}")
    
    except Exception as e:
        print(f"Exception occurred: {str(e)}")

if __name__ == "__main__":
    main() 