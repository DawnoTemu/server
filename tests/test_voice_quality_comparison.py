#!/usr/bin/env python
import sys
import os
from dotenv import load_dotenv
import time
from io import BytesIO
import json
import requests

# Ensure we're in the correct directory for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables from .env file
load_dotenv()

from utils.elevenlabs_service import ElevenLabsService
from utils.cartesia_sdk_service import CartesiaSDKService
from config import Config
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Polish text for synthesis (about 30 seconds)
POLISH_TEXT = """
W sercu polskiego krajobrazu, pośród zielonych łąk i rozległych lasów, znajduje się malownicza wioska. 
Jej mieszkańcy od pokoleń żyją w harmonii z naturą, pielęgnując dawne tradycje i zwyczaje.
Każdego ranka, gdy słońce wznosi się nad horyzontem, wioska budzi się do życia. 
Rolnicy wyruszają na pola, rzemieślnicy otwierają swoje warsztaty, a dzieci biegną do szkoły wąskimi, brukowanymi uliczkami.
Popołudniami na głównym placu można spotkać starszych mieszkańców, którzy dzielą się historiami z przeszłości. 
Ich opowieści przesiąknięte są mądrością wielu pokoleń i stanowią żywe świadectwo bogatej kultury tego regionu.
W oddali, na wzgórzu, stoi stary kościół z wieżą, która góruje nad okolicą. 
Jego dzwony odmierzają rytm codziennego życia, wzywając na modlitwę i oznajmiając ważne wydarzenia.
"""

def setup_directory():
    """Create a directory to store the test results"""
    timestamp = int(time.time())
    test_dir = f"voice_quality_test_{timestamp}"
    os.makedirs(test_dir, exist_ok=True)
    return test_dir

def load_voice_sample():
    """Load the voice sample file"""
    try:
        sample_path = "001.mp3"
        if not os.path.exists(sample_path):
            print(f"❌ Voice sample {sample_path} not found")
            return None
            
        print(f"Loading voice sample from {sample_path}...")
        with open(sample_path, "rb") as f:
            return BytesIO(f.read())
    except Exception as e:
        print(f"❌ Error loading voice sample: {str(e)}")
        return None

def clone_elevenlabs_voice(voice_data, enhance, test_dir):
    """Clone a voice using ElevenLabs"""
    try:
        voice_name = f"ElevenLabs_{'Enhanced' if enhance else 'Normal'}"
        print(f"Cloning voice with ElevenLabs ({voice_name})...")
        
        # Prepare the file in the format expected by ElevenLabs
        # ElevenLabs expects a list of tuples: [(filename, file_data, mime_type), ...]
        voice_data.seek(0)
        mime_type = "audio/mpeg"
        files = [("001.mp3", voice_data, mime_type)]
        
        # Clone the voice with ElevenLabs
        success, result = ElevenLabsService.clone_voice(
            files=files,
            voice_name=voice_name,
            voice_description=f"Test voice with enhancement={enhance}",
            remove_background_noise=enhance
        )
        
        if success:
            voice_id = result.get("voice_id")
            print(f"✅ ElevenLabs voice cloned successfully: {voice_id}")
            
            # Save voice details for reference
            voice_details = {
                "service": "ElevenLabs",
                "enhancement": enhance,
                "voice_id": voice_id,
                "voice_name": voice_name
            }
            
            with open(f"{test_dir}/{voice_name}_details.json", 'w') as f:
                json.dump(voice_details, f, indent=2)
                
            return voice_id
        else:
            print(f"❌ ElevenLabs voice cloning failed: {result}")
            return None
    except Exception as e:
        print(f"❌ Exception in ElevenLabs cloning: {str(e)}")
        return None

def clone_cartesia_voice(voice_data, enhance, mode, test_dir):
    """Clone a voice using Cartesia"""
    try:
        voice_name = f"Cartesia_{mode.capitalize()}_{'Enhanced' if enhance else 'Normal'}"
        print(f"Cloning voice with Cartesia ({voice_name}, mode={mode})...")
        
        # We need to reset the file position to beginning
        voice_data.seek(0)
        
        # Create the file tuple for Cartesia
        files = [("001.mp3", voice_data, "audio/mpeg")]
        
        # Clone the voice with Cartesia
        success, result = CartesiaSDKService.clone_voice(
            files=files,
            voice_name=voice_name,
            voice_description=f"Test voice with enhancement={enhance}, mode={mode}",
            language="pl",
            mode=mode,
            enhance=enhance
        )
        
        if success:
            voice_id = result.get("voice_id")
            print(f"✅ Cartesia voice cloned successfully: {voice_id}")
            
            # Save voice details for reference
            voice_details = {
                "service": "Cartesia",
                "enhancement": enhance,
                "mode": mode,
                "voice_id": voice_id,
                "voice_name": voice_name
            }
            
            with open(f"{test_dir}/{voice_name}_details.json", 'w') as f:
                json.dump(voice_details, f, indent=2)
                
            return voice_id
        else:
            print(f"❌ Cartesia voice cloning failed: {result}")
            return None
    except Exception as e:
        print(f"❌ Exception in Cartesia cloning: {str(e)}")
        return None

def synthesize_elevenlabs_speech(voice_id, voice_name, test_dir, model_id="eleven_multilingual_v2"):
    """Synthesize speech using ElevenLabs"""
    try:
        model_suffix = "_multilingual" if model_id == "eleven_multilingual_v2" else "_flash"
        output_name = f"{voice_name}{model_suffix}"
        
        print(f"Synthesizing speech with ElevenLabs voice {voice_name} using model {model_id}...")
        
        # We need to directly call the ElevenLabs API since the service function doesn't accept a model_id parameter
        session = requests.Session()
        session.headers.update({"xi-api-key": Config.ELEVENLABS_API_KEY})
        
        # Use a session with keep-alive for better performance
        response = session.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream",
            json={
                "text": POLISH_TEXT,
                "model_id": model_id,
                "voice_settings": {
                    "stability": 0.65,
                    "similarity_boost": 0.9,
                    "style": 0.1,
                    "use_speaker_boost": True,
                    "speed": 1.0
                }
            },
            headers={"Accept": "audio/mpeg"}
        )
        
        if response.status_code == 200:
            # Save the audio to a file
            output_filename = f"{test_dir}/{output_name}_synthesis.mp3"
            
            print(f"Writing ElevenLabs audio to {output_filename}...")
            with open(output_filename, 'wb') as f:
                f.write(response.content)
                
            print(f"✅ ElevenLabs speech synthesis successful with model {model_id}!")
            return output_filename
        else:
            print(f"❌ ElevenLabs speech synthesis failed: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Exception in ElevenLabs synthesis: {str(e)}")
        return None

def synthesize_cartesia_speech(voice_id, voice_name, test_dir):
    """Synthesize speech using Cartesia"""
    try:
        print(f"Synthesizing speech with Cartesia voice {voice_name}...")
        
        # Synthesize the speech
        success, result = CartesiaSDKService.synthesize_speech(
            cartesia_voice_id=voice_id,
            text=POLISH_TEXT,
            model_id="sonic-2",
            language="pl",
            speed="normal"  # Using slow for Polish to improve quality
        )
        
        if success:
            # Save the audio to a file
            output_filename = f"{test_dir}/{voice_name}_synthesis.mp3"
            
            print(f"Writing Cartesia audio to {output_filename}...")
            with open(output_filename, 'wb') as f:
                f.write(result.getvalue())
                
            print(f"✅ Cartesia speech synthesis successful!")
            return output_filename
        else:
            print(f"❌ Cartesia speech synthesis failed: {result}")
            return None
    except Exception as e:
        print(f"❌ Exception in Cartesia synthesis: {str(e)}")
        return None

def main():
    print("Starting voice quality comparison test...")
    
    # Create test directory
    test_dir = setup_directory()
    print(f"Test results will be saved in: {test_dir}")
    
    # Load voice sample
    voice_data = load_voice_sample()
    if not voice_data:
        return
    
    # Clone voices
    print("\n=== CLONING VOICES ===\n")
    
    # ElevenLabs with and without enhancement
    elevenlabs_enhanced_voice_id = clone_elevenlabs_voice(voice_data, True, test_dir)
    voice_data.seek(0)  # Reset position
    elevenlabs_normal_voice_id = clone_elevenlabs_voice(voice_data, False, test_dir)
    
    # Cartesia with SIMILARITY mode (with and without enhancement)
    voice_data.seek(0)  # Reset position
    cartesia_similarity_enhanced_voice_id = clone_cartesia_voice(voice_data, True, "similarity", test_dir)
    voice_data.seek(0)  # Reset position
    cartesia_similarity_normal_voice_id = clone_cartesia_voice(voice_data, False, "similarity", test_dir)
    
    # Cartesia with STABILITY mode (with and without enhancement)
    voice_data.seek(0)  # Reset position
    cartesia_stability_enhanced_voice_id = clone_cartesia_voice(voice_data, True, "stability", test_dir)
    voice_data.seek(0)  # Reset position
    cartesia_stability_normal_voice_id = clone_cartesia_voice(voice_data, False, "stability", test_dir)
    
    # Synthesize speech
    print("\n=== SYNTHESIZING SPEECH ===\n")
    
    # Check which voices were successfully cloned
    results = {}
    
    # ElevenLabs voices with both models
    if elevenlabs_enhanced_voice_id:
        # Test with eleven_multilingual_v2 model
        multilingual_result = synthesize_elevenlabs_speech(
            elevenlabs_enhanced_voice_id, 
            "ElevenLabs_Enhanced", 
            test_dir,
            "eleven_multilingual_v2"
        )
        if multilingual_result:
            results["ElevenLabs Enhanced (Multilingual)"] = multilingual_result
            
        # Test with eleven_flash_v2_5 model
        flash_result = synthesize_elevenlabs_speech(
            elevenlabs_enhanced_voice_id, 
            "ElevenLabs_Enhanced", 
            test_dir,
            "eleven_flash_v2_5"
        )
        if flash_result:
            results["ElevenLabs Enhanced (Flash)"] = flash_result
    
    if elevenlabs_normal_voice_id:
        # Test with eleven_multilingual_v2 model
        multilingual_result = synthesize_elevenlabs_speech(
            elevenlabs_normal_voice_id, 
            "ElevenLabs_Normal", 
            test_dir,
            "eleven_multilingual_v2"
        )
        if multilingual_result:
            results["ElevenLabs Normal (Multilingual)"] = multilingual_result
            
        # Test with eleven_flash_v2_5 model
        flash_result = synthesize_elevenlabs_speech(
            elevenlabs_normal_voice_id, 
            "ElevenLabs_Normal", 
            test_dir,
            "eleven_flash_v2_5"
        )
        if flash_result:
            results["ElevenLabs Normal (Flash)"] = flash_result
    
    # Cartesia Similarity voices
    if cartesia_similarity_enhanced_voice_id:
        result = synthesize_cartesia_speech(
            cartesia_similarity_enhanced_voice_id, 
            "Cartesia_Similarity_Enhanced", 
            test_dir
        )
        if result:
            results["Cartesia Similarity Enhanced"] = result
    
    if cartesia_similarity_normal_voice_id:
        result = synthesize_cartesia_speech(
            cartesia_similarity_normal_voice_id, 
            "Cartesia_Similarity_Normal", 
            test_dir
        )
        if result:
            results["Cartesia Similarity Normal"] = result
    
    # Cartesia Stability voices
    if cartesia_stability_enhanced_voice_id:
        result = synthesize_cartesia_speech(
            cartesia_stability_enhanced_voice_id, 
            "Cartesia_Stability_Enhanced", 
            test_dir
        )
        if result:
            results["Cartesia Stability Enhanced"] = result
    
    if cartesia_stability_normal_voice_id:
        result = synthesize_cartesia_speech(
            cartesia_stability_normal_voice_id, 
            "Cartesia_Stability_Normal", 
            test_dir
        )
        if result:
            results["Cartesia Stability Normal"] = result
    
    # Summary
    print("\n=== TEST SUMMARY ===\n")
    print(f"Test completed. Results saved in directory: {test_dir}")
    print(f"Generated files:")
    
    for service, filepath in results.items():
        print(f"- {service}: {os.path.basename(filepath)}")
    
    # Create a README for the test directory
    with open(f"{test_dir}/README.md", 'w') as f:
        f.write("# Voice Quality Comparison Test\n\n")
        f.write(f"Test conducted on: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("## Test Configuration\n\n")
        f.write("- Original voice sample: 001.mp3\n")
        f.write("- Text length: ~30 seconds\n")
        f.write("- Language: Polish\n\n")
        f.write("## Voice Services\n\n")
        
        # Group ElevenLabs models by voice
        f.write("### ElevenLabs (Enhanced Voice)\n")
        for service, filepath in results.items():
            if "ElevenLabs Enhanced" in service:
                f.write(f"- {service}: [{os.path.basename(filepath)}]({os.path.basename(filepath)})\n")
        
        f.write("\n### ElevenLabs (Normal Voice)\n")
        for service, filepath in results.items():
            if "ElevenLabs Normal" in service:
                f.write(f"- {service}: [{os.path.basename(filepath)}]({os.path.basename(filepath)})\n")
        
        f.write("\n### Cartesia Similarity Mode\n")
        for service, filepath in results.items():
            if "Similarity" in service:
                f.write(f"- {service}: [{os.path.basename(filepath)}]({os.path.basename(filepath)})\n")
        
        f.write("\n### Cartesia Stability Mode\n")
        for service, filepath in results.items():
            if "Stability" in service:
                f.write(f"- {service}: [{os.path.basename(filepath)}]({os.path.basename(filepath)})\n")
                
        f.write("\n## Text Used\n\n")
        f.write("```\n")
        f.write(POLISH_TEXT)
        f.write("\n```\n")
        
        f.write("\n## Model Information\n\n")
        f.write("### ElevenLabs Models\n")
        f.write("- **eleven_multilingual_v2**: Supports multiple languages and is optimized for naturalness\n")
        f.write("- **eleven_flash_v2_5**: Faster generation with good quality for single-language use\n\n")
        
        f.write("### Cartesia Modes\n")
        f.write("- **similarity**: Prioritizes matching the original voice's characteristics\n")
        f.write("- **stability**: Prioritizes consistency in generation with fewer artifacts\n")
    
    print("\nOpen the generated audio files with a media player to compare the quality.")

if __name__ == "__main__":
    main() 