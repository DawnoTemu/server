# Cartesia Integration Notes

## Overview

This document outlines the implementation of voice cloning and speech synthesis using the Cartesia API through their official SDK.

## Challenges Faced

1. **SDK Version Differences** - The Cartesia SDK appears to have different APIs between versions. Our current version is 2.0.3.

2. **Output Format Issues** - The `bytes()` method requires an `output_format` parameter with very specific fields that must match the API specifications.

3. **API Error Handling** - API errors (especially 402 Payment Required) need explicit handling to provide user-friendly messages.

4. **Generator Response** - The SDK returns a generator which needs to be properly consumed to get the audio bytes.

## Implementation Details

### Voice Cloning

Voice cloning is implemented in `CartesiaSDKService.clone_voice()` which:

1. Uses the Cartesia SDK to clone a voice from an audio sample
2. Provides clear error messages, especially for payment/credit issues
3. Returns a consistent response format compatible with the VoiceService facade

### Speech Synthesis

Speech synthesis is implemented in `CartesiaSDKService.synthesize_speech()` which:

1. Uses the exact output format specification required by the API:
   ```json
   "output_format": {
     "container": "mp3",
     "bit_rate": 128000,
     "sample_rate": 44100
   }
   ```
2. Properly structures the voice object with `mode: "id"` as per API documentation
3. Properly consumes the generator response to collect audio data
4. Provides robust error handling with user-friendly messages
5. Returns audio as a BytesIO object for consistent handling

## API Documentation References

For Speech Synthesis specifically, refer to the [official Cartesia API documentation](https://docs.cartesia.ai/2024-11-13/api-reference/tts/bytes) for the `/tts/bytes` endpoint which specifies the exact output format structure required.

## Testing

Two test scripts are provided:

1. `test_cartesia_voices.py` - Lists all voices in your Cartesia account
2. `test_cartesia_synthesis.py` - Tests speech synthesis with a specific voice

## Recommendations

1. Keep the Cartesia SDK updated to the latest version
2. Monitor API usage and credits to prevent 402 errors
3. Consider implementing a fallback to an alternative service (e.g., ElevenLabs) when Cartesia API issues occur
4. Always refer to the official API documentation for parameter formats

## API Limits and Billing

The 402 error indicates payment/credit issues with your Cartesia account. If you encounter this error:

1. Check your account balance in the Cartesia dashboard
2. Review API usage limits
3. Consider upgrading your plan if necessary 