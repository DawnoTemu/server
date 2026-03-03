"""
Mock ElevenLabs HTTP server for local load testing.

Simulates the ElevenLabs TTS API with configurable:
  - Latency (min/max)
  - Error rate
  - Rate limiting (429 after N concurrent requests)
  - Voice CRUD operations

Run standalone:
  python -m tests.load.mock_elevenlabs_server

Environment variables:
  MOCK_EL_LATENCY_MIN  - Minimum synthesis latency in seconds (default: 2)
  MOCK_EL_LATENCY_MAX  - Maximum synthesis latency in seconds (default: 5)
  MOCK_EL_ERROR_RATE   - Probability of returning a 500 error (default: 0.05)
  MOCK_EL_RATE_LIMIT_AFTER - Max concurrent synth before 429 (default: 5)
  MOCK_EL_PORT         - Server port (default: 11411)
"""

import logging
import os
import random
import threading
import time
import uuid

from flask import Flask, jsonify, request

logger = logging.getLogger("mock_elevenlabs")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LATENCY_MIN = float(os.getenv("MOCK_EL_LATENCY_MIN", "2"))
LATENCY_MAX = float(os.getenv("MOCK_EL_LATENCY_MAX", "5"))
ERROR_RATE = float(os.getenv("MOCK_EL_ERROR_RATE", "0.05"))
RATE_LIMIT_AFTER = int(os.getenv("MOCK_EL_RATE_LIMIT_AFTER", "5"))
PORT = int(os.getenv("MOCK_EL_PORT", "11411"))

# ---------------------------------------------------------------------------
# Concurrency tracking
# ---------------------------------------------------------------------------

_concurrent_synth = 0
_concurrent_lock = threading.Lock()

# ---------------------------------------------------------------------------
# In-memory voice store
# ---------------------------------------------------------------------------

_voices: dict[str, dict] = {}
_voices_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app = Flask(__name__)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "concurrent_synth": _concurrent_synth})


@app.route("/v1/text-to-speech/<voice_id>", methods=["POST"])
def synthesize(voice_id: str):
    """
    Simulate ElevenLabs TTS synthesis.
    Returns a fake MP3 after a configurable delay.
    """
    global _concurrent_synth

    with _concurrent_lock:
        if _concurrent_synth >= RATE_LIMIT_AFTER:
            logger.info("Rate limiting: %d concurrent synth requests", _concurrent_synth)
            return jsonify({
                "detail": {
                    "status": "too_many_concurrent_requests",
                    "message": "Too many concurrent requests. Please try again later.",
                },
            }), 429
        _concurrent_synth += 1

    try:
        # Simulate random errors
        if random.random() < ERROR_RATE:
            logger.info("Simulating error for voice %s", voice_id)
            return jsonify({"error": "Internal server error (simulated)"}), 500

        # Simulate synthesis latency
        latency = random.uniform(LATENCY_MIN, LATENCY_MAX)
        time.sleep(latency)

        # Generate a fake MP3 response (minimal valid-ish bytes)
        # Real MP3 header: FF FB 90 00 ...
        fake_mp3 = b"\xff\xfb\x90\x00" + os.urandom(8192)

        logger.info(
            "Synthesized for voice %s in %.1fs (%d bytes)",
            voice_id,
            latency,
            len(fake_mp3),
        )

        return fake_mp3, 200, {"Content-Type": "audio/mpeg"}

    finally:
        with _concurrent_lock:
            _concurrent_synth -= 1


@app.route("/v1/voices/add", methods=["POST"])
def add_voice():
    """Simulate adding a voice clone."""
    voice_id = str(uuid.uuid4())
    name = request.form.get("name", "Test Voice")

    with _voices_lock:
        _voices[voice_id] = {
            "voice_id": voice_id,
            "name": name,
            "category": "cloned",
        }

    logger.info("Created mock voice: %s (%s)", voice_id, name)

    # Simulate small delay for voice processing
    time.sleep(random.uniform(0.5, 1.5))

    return jsonify({"voice_id": voice_id}), 200


@app.route("/v1/voices/<voice_id>", methods=["GET"])
def get_voice(voice_id: str):
    """Get voice details."""
    with _voices_lock:
        voice = _voices.get(voice_id)
    if voice:
        return jsonify(voice), 200
    return jsonify({"detail": {"message": "Voice not found"}}), 404


@app.route("/v1/voices/<voice_id>", methods=["DELETE"])
def delete_voice(voice_id: str):
    """Delete a voice clone."""
    with _voices_lock:
        removed = _voices.pop(voice_id, None)

    if removed:
        logger.info("Deleted mock voice: %s", voice_id)
        return jsonify({"status": "ok"}), 200

    # ElevenLabs returns 200 even for non-existent voices
    return jsonify({"status": "ok"}), 200


@app.route("/v1/voices", methods=["GET"])
def list_voices():
    """List all voices."""
    with _voices_lock:
        voices = list(_voices.values())
    return jsonify({"voices": voices}), 200


# ---------------------------------------------------------------------------
# Metrics endpoint (for load test monitoring)
# ---------------------------------------------------------------------------

@app.route("/metrics", methods=["GET"])
def metrics():
    """Return internal metrics for monitoring during load tests."""
    with _voices_lock:
        voice_count = len(_voices)
    return jsonify({
        "concurrent_synth": _concurrent_synth,
        "rate_limit_threshold": RATE_LIMIT_AFTER,
        "voice_count": voice_count,
        "latency_range": [LATENCY_MIN, LATENCY_MAX],
        "error_rate": ERROR_RATE,
    })


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info(
        "Starting mock ElevenLabs server on port %d "
        "(latency=%.1f-%.1fs, error_rate=%.2f, rate_limit_after=%d)",
        PORT,
        LATENCY_MIN,
        LATENCY_MAX,
        ERROR_RATE,
        RATE_LIMIT_AFTER,
    )
    app.run(host="0.0.0.0", port=PORT, threaded=True)
