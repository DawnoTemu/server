#!/usr/bin/env python3
"""
StoryVoice RESTful API Test Script

This script tests all RESTful endpoints for the StoryVoice application,
simulating a complete user flow from registration to audio generation.

Prerequisites:
    - Install requirements: pip install requests
    - Have the StoryVoice server running locally at http://localhost:8000
    - Have a test.wav or test.mp3 file in the same directory for voice cloning

Usage:
    python test_endpoints.py [--base-url=http://localhost:8000] [--audio-file=test.wav]
"""

import os
import sys
import json
import time
import argparse
import requests
from pprint import pprint
from urllib.parse import urljoin

# Default configuration
DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_AUDIO_FILE = "test.wav"  # A sample audio file for voice cloning
TEST_EMAIL = "test_user@example.com"
TEST_PASSWORD = "Test@Password123"

# Test state
auth_tokens = {
    "access_token": None,
    "refresh_token": None
}
test_voice_id = None
test_story_id = 1  # Assuming there's at least one story in the database


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Test StoryVoice RESTful API endpoints")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Base URL of the StoryVoice API")
    parser.add_argument("--audio-file", default=DEFAULT_AUDIO_FILE, help="Audio file for voice cloning test")
    return parser.parse_args()


def make_request(method, endpoint, headers=None, params=None, data=None, files=None, json_data=None, expected_status=None):
    """Make a request to the API and handle errors consistently"""
    if headers is None and auth_tokens["access_token"]:
        headers = {"Authorization": f"Bearer {auth_tokens['access_token']}"}
    
    url = urljoin(args.base_url, endpoint)
    
    print(f"\n{'=' * 80}")
    print(f"REQUEST: {method} {url}")
    if params:
        print(f"Params: {params}")
    if data:
        print(f"Data: {data}")
    if json_data:
        print(f"JSON: {json_data}")
    if files:
        print(f"Files: {list(files.keys())}")
    print(f"{'=' * 80}")
    
    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            data=data,
            files=files,
            json=json_data,
            timeout=30
        )
        
        print(f"RESPONSE: Status {response.status_code}")
        
        # Check if this is a JSON response
        content_type = response.headers.get('Content-Type', '')
        if 'application/json' in content_type:
            try:
                response_data = response.json()
                print("Response data:")
                pprint(response_data)
            except json.JSONDecodeError:
                print(f"Response (not JSON): {response.text[:1000]}")
        elif len(response.content) < 1000:
            print(f"Response: {response.text}")
        else:
            print(f"Response: [Binary data or long text, length: {len(response.content)} bytes]")
        
        # Check status code if expected
        if expected_status and response.status_code != expected_status:
            print(f"WARNING: Expected status {expected_status}, got {response.status_code}")
        
        return response
    
    except requests.exceptions.RequestException as e:
        print(f"ERROR: {str(e)}")
        return None


def test_register_user():
    """Test user registration"""
    print("\n\n--- Testing User Registration ---")
    
    response = make_request(
        method="POST",
        endpoint="/auth/register",
        json_data={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
            "password_confirm": TEST_PASSWORD
        }
    )
    
    if response and response.status_code in (201, 200):
        print("User registration successful or user already exists")
        return True
    elif response and response.status_code == 409:
        print("User already exists, proceeding to login")
        return True
    else:
        print("Failed to register user")
        return False


def test_login():
    """Test user login and token retrieval"""
    print("\n\n--- Testing User Login ---")
    
    response = make_request(
        method="POST",
        endpoint="/auth/login",
        json_data={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        },
        expected_status=200
    )
    
    if response and response.status_code == 200:
        data = response.json()
        auth_tokens["access_token"] = data.get("access_token")
        auth_tokens["refresh_token"] = data.get("refresh_token")
        
        if auth_tokens["access_token"]:
            print("Login successful, retrieved access token")
            return True
    
    print("Failed to login")
    return False


def test_get_current_user():
    """Test getting current user info with the token"""
    print("\n\n--- Testing Get Current User ---")
    
    response = make_request(
        method="GET",
        endpoint="/auth/me",
        expected_status=200
    )
    
    if response and response.status_code == 200:
        print("Successfully retrieved user info")
        return True
    
    print("Failed to get user info")
    return False


def test_list_stories():
    """Test listing all available stories"""
    global test_story_id
    print("\n\n--- Testing List Stories ---")
    
    response = make_request(
        method="GET",
        endpoint="/stories",
        expected_status=200
    )
    
    if response and response.status_code == 200:
        stories = response.json()
        
        if stories and len(stories) > 0:
            test_story_id = stories[0].get("id", test_story_id)
            print(f"Successfully retrieved stories, using story ID: {test_story_id}")
            return True
    
    print("Failed to list stories or no stories available")
    return False


def test_get_story():
    """Test getting a specific story"""
    print(f"\n\n--- Testing Get Story (ID: {test_story_id}) ---")
    
    response = make_request(
        method="GET",
        endpoint=f"/stories/{test_story_id}",
        expected_status=200
    )
    
    if response and response.status_code == 200:
        print("Successfully retrieved story details")
        return True
    
    print("Failed to get story details")
    return False


def test_clone_voice():
    """Test voice cloning with an audio file"""
    global test_voice_id
    print("\n\n--- Testing Voice Cloning ---")
    
    # Check if the audio file exists
    if not os.path.exists(args.audio_file):
        print(f"Audio file {args.audio_file} not found")
        return False
    
    with open(args.audio_file, "rb") as f:
        response = make_request(
            method="POST",
            endpoint="/voices",
            files={
                "file": (os.path.basename(args.audio_file), f, 
                        "audio/wav" if args.audio_file.endswith(".wav") else "audio/mpeg")
            },
            data={
                "name": "Test Voice"
            },
            expected_status=200
        )
    
    if response and response.status_code == 200:
        data = response.json()
        test_voice_id = data.get("id")
        elevenlabs_voice_id = data.get("voice_id")
        
        if test_voice_id:
            print(f"Successfully cloned voice, ID: {test_voice_id}, ElevenLabs ID: {elevenlabs_voice_id}")
            return True
    
    print("Failed to clone voice")
    return False


def test_list_voices():
    """Test listing all voices for the current user"""
    global test_voice_id
    print("\n\n--- Testing List Voices ---")
    
    response = make_request(
        method="GET",
        endpoint="/voices",
        expected_status=200
    )
    
    if response and response.status_code == 200:
        voices = response.json()
        
        if test_voice_id is None and voices and len(voices) > 0:
            test_voice_id = voices[0].get("id")
            print(f"Using existing voice with ID: {test_voice_id}")
        
        print(f"Successfully retrieved {len(voices)} voices")
        return True
    
    print("Failed to list voices")
    return False


def test_get_voice():
    """Test getting a specific voice"""
    if not test_voice_id:
        print("No voice ID available, skipping get voice test")
        return False
    
    print(f"\n\n--- Testing Get Voice (ID: {test_voice_id}) ---")
    
    response = make_request(
        method="GET",
        endpoint=f"/voices/{test_voice_id}",
        expected_status=200
    )
    
    if response and response.status_code == 200:
        voice_data = response.json()
        elevenlabs_voice_id = voice_data.get("elevenlabs_voice_id")
        print(f"Successfully retrieved voice details, ElevenLabs ID: {elevenlabs_voice_id}")
        return True
    
    print("Failed to get voice details")
    return False


def test_get_voice_sample():
    """Test getting the voice sample audio"""
    if not test_voice_id:
        print("No voice ID available, skipping voice sample test")
        return False
    
    print(f"\n\n--- Testing Get Voice Sample (ID: {test_voice_id}) ---")
    
    response = make_request(
        method="GET",
        endpoint=f"/voices/{test_voice_id}/sample",
        expected_status=200
    )
    
    if response and response.status_code == 200:
        print("Successfully retrieved voice sample URL")
        return True
    
    print("Failed to get voice sample")
    return False


def test_check_audio_exists():
    """Test checking if audio exists for a story/voice combination"""
    if not test_voice_id:
        print("No voice ID available, skipping audio check test")
        return False
    
    # Get the ElevenLabs voice ID from the voice details
    response = make_request(
        method="GET",
        endpoint=f"/voices/{test_voice_id}",
        expected_status=200
    )
    
    if not response or response.status_code != 200:
        print("Failed to get voice details for audio check")
        return False
    
    voice_data = response.json()
    elevenlabs_voice_id = voice_data.get("elevenlabs_voice_id")
    
    if not elevenlabs_voice_id:
        print("No ElevenLabs voice ID available")
        return False
    
    print(f"\n\n--- Testing Check Audio Exists (Voice: {elevenlabs_voice_id}, Story: {test_story_id}) ---")
    
    response = make_request(
        method="HEAD",
        endpoint=f"/voices/{elevenlabs_voice_id}/stories/{test_story_id}/audio",
        expected_status=(200, 404)  # Both are valid responses
    )
    
    if response:
        if response.status_code == 200:
            print("Audio already exists")
        else:
            print("Audio does not exist yet, will need to synthesize")
        return True
    
    print("Failed to check audio existence")
    return False


def test_synthesize_audio():
    """Test synthesizing audio for a story with a voice"""
    if not test_voice_id:
        print("No voice ID available, skipping audio synthesis test")
        return False
    
    # Get the ElevenLabs voice ID
    response = make_request(
        method="GET",
        endpoint=f"/voices/{test_voice_id}",
        expected_status=200
    )
    
    if not response or response.status_code != 200:
        print("Failed to get voice details for synthesis")
        return False
    
    voice_data = response.json()
    elevenlabs_voice_id = voice_data.get("elevenlabs_voice_id")
    
    if not elevenlabs_voice_id:
        print("No ElevenLabs voice ID available")
        return False
    
    print(f"\n\n--- Testing Synthesize Audio (Voice: {elevenlabs_voice_id}, Story: {test_story_id}) ---")
    
    response = make_request(
        method="POST",
        endpoint=f"/voices/{elevenlabs_voice_id}/stories/{test_story_id}/audio",
        expected_status=200
    )
    
    if response and response.status_code == 200:
        print("Successfully requested audio synthesis")
        # Wait a moment for synthesis to complete
        print("Waiting for audio synthesis to complete...")
        time.sleep(5)  # This might need to be longer depending on the story length
        return True
    
    print("Failed to synthesize audio")
    return False


def test_get_audio():
    """Test streaming the synthesized audio"""
    if not test_voice_id:
        print("No voice ID available, skipping get audio test")
        return False
    
    # Get the ElevenLabs voice ID
    response = make_request(
        method="GET",
        endpoint=f"/voices/{test_voice_id}",
        expected_status=200
    )
    
    if not response or response.status_code != 200:
        print("Failed to get voice details for audio streaming")
        return False
    
    voice_data = response.json()
    elevenlabs_voice_id = voice_data.get("elevenlabs_voice_id")
    
    if not elevenlabs_voice_id:
        print("No ElevenLabs voice ID available")
        return False
    
    print(f"\n\n--- Testing Get Audio (Voice: {elevenlabs_voice_id}, Story: {test_story_id}) ---")
    
    # First check if audio exists using HEAD
    head_response = make_request(
        method="HEAD",
        endpoint=f"/voices/{elevenlabs_voice_id}/stories/{test_story_id}/audio"
    )
    
    if head_response and head_response.status_code != 200:
        print("Audio does not exist, trying to synthesize first")
        test_synthesize_audio()
    
    # Now try to get the audio with redirect
    response = make_request(
        method="GET",
        endpoint=f"/voices/{elevenlabs_voice_id}/stories/{test_story_id}/audio",
        params={"redirect": "true"},
        expected_status=(200, 302)
    )
    
    if response and response.status_code in (200, 302):
        print("Successfully retrieved audio URL")
        return True
    
    print("Failed to get audio")
    return False


def test_delete_voice():
    """Test deleting a voice"""
    if not test_voice_id:
        print("No voice ID available, skipping delete test")
        return False
    
    print(f"\n\n--- Testing Delete Voice (ID: {test_voice_id}) ---")
    
    response = make_request(
        method="DELETE",
        endpoint=f"/voices/{test_voice_id}",
        expected_status=200
    )
    
    if response and response.status_code == 200:
        print("Successfully deleted voice")
        return True
    
    print("Failed to delete voice")
    return False


def test_refresh_token():
    """Test refreshing the access token"""
    if not auth_tokens["refresh_token"]:
        print("No refresh token available, skipping token refresh test")
        return False
    
    print("\n\n--- Testing Refresh Token ---")
    
    response = make_request(
        method="POST",
        endpoint="/auth/refresh",
        headers={},  # Don't use the access token for this request
        json_data={
            "refresh_token": auth_tokens["refresh_token"]
        },
        expected_status=200
    )
    
    if response and response.status_code == 200:
        data = response.json()
        new_access_token = data.get("access_token")
        
        if new_access_token:
            auth_tokens["access_token"] = new_access_token
            print("Successfully refreshed access token")
            return True
    
    print("Failed to refresh token")
    return False


def run_all_tests():
    """Run all API tests in sequence"""
    tests = [
        ("Registration", test_register_user),
        ("Login", test_login),
        ("Get Current User", test_get_current_user),
        ("List Stories", test_list_stories),
        ("Get Story", test_get_story),
        ("Clone Voice", test_clone_voice),
        ("List Voices", test_list_voices),
        ("Get Voice", test_get_voice),
        ("Get Voice Sample", test_get_voice_sample),
        ("Check Audio Exists", test_check_audio_exists),
        ("Synthesize Audio", test_synthesize_audio),
        ("Get Audio", test_get_audio),
        ("Refresh Token", test_refresh_token),
        ("Delete Voice", test_delete_voice),
    ]
    
    results = {}
    all_passed = True
    
    for name, test_func in tests:
        print(f"\n\n{'#' * 80}")
        print(f"# Starting Test: {name}")
        print(f"{'#' * 80}")
        
        try:
            result = test_func()
            results[name] = "PASS" if result else "FAIL"
            if not result:
                all_passed = False
        except Exception as e:
            print(f"Exception during test: {str(e)}")
            results[name] = "ERROR"
            all_passed = False
    
    print("\n\n")
    print("="*80)
    print("TEST RESULTS SUMMARY")
    print("="*80)
    
    for name, result in results.items():
        status_color = "\033[92m" if result == "PASS" else "\033[91m"  # Green for pass, red for fail
        reset_color = "\033[0m"
        print(f"{name:.<30} {status_color}{result}{reset_color}")
    
    print("="*80)
    
    if all_passed:
        print("\033[92mALL TESTS PASSED\033[0m")
        return 0
    else:
        print("\033[91mSOME TESTS FAILED\033[0m")
        return 1


if __name__ == "__main__":
    args = parse_args()
    sys.exit(run_all_tests())