#!/usr/bin/env python
import sys
import os
from dotenv import load_dotenv

# Ensure we're in the correct directory for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables from .env file
load_dotenv()

from cartesia import Cartesia

def main():
    # Get API key
    api_key = os.getenv("CARTESIA_API_KEY")
    if not api_key:
        print("❌ CARTESIA_API_KEY environment variable not set")
        return
        
    print("Creating Cartesia client...")
    client = Cartesia(api_key=api_key)
    
    # Inspect client object
    print("\n=== Cartesia Client ===")
    print(f"Client type: {type(client)}")
    print(f"Client dir: {dir(client)}")
    
    # Inspect TTS object
    print("\n=== TTS Client ===")
    print(f"TTS type: {type(client.tts)}")
    print(f"TTS dir: {dir(client.tts)}")
    
    # If voices property exists, inspect it too
    if hasattr(client, 'voices'):
        print("\n=== Voices Client ===")
        print(f"Voices type: {type(client.voices)}")
        print(f"Voices dir: {dir(client.voices)}")
    
    print("\nThis information will help us identify the correct methods to use for synthesis.")

if __name__ == "__main__":
    main() 