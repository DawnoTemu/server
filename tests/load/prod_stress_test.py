"""
Production stress test: real voice cloning + audio synthesis.

Uses a real voice sample (001.mp3) to test the full pipeline:
  1. Login as pre-created test users (created via setup_test_data.py)
  2. Delete any fake/existing voices
  3. Upload voice sample (POST /voices) -> real voice clone
  4. Wait for voice allocation
  5. Request audio synthesis for stories
  6. Poll until audio is ready
  7. Clean up (delete voices via API, users via Render job)

Prerequisites:
  Run setup_test_data.py on production first to create users:
    render jobs create <service-id> --start-command "python -m tests.load.setup_test_data"

Usage:
  .venv/bin/python -m tests.load.prod_stress_test \
    --base-url https://server-pf6p.onrender.com \
    --users 2 --stories 1

  # Cleanup only (deletes voices, not users - use Render job for that):
  .venv/bin/python -m tests.load.prod_stress_test \
    --base-url https://server-pf6p.onrender.com --cleanup-only
"""

import argparse
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s [%(threadName)s] %(message)s",
)
logger = logging.getLogger("prod_stress")

# ---------------------------------------------------------------------------
# Configuration — must match setup_test_data.py / config.py
# ---------------------------------------------------------------------------

EMAIL_TEMPLATE = "loadtest+{n}@dawnotemu.test"
PASSWORD = "LoadTest2024!"

POLL_INTERVAL = 5
POLL_TIMEOUT = 600  # 10 min
VOICE_READY_TIMEOUT = 180  # 3 min for voice allocation


# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------

@dataclass
class UserResult:
    user_num: int
    email: str = ""
    user_id: int = 0
    voice_id: int = 0
    voice_upload_sec: float = 0.0
    voice_ready_sec: float = 0.0
    synth_results: list = field(default_factory=list)
    errors: list = field(default_factory=list)


@dataclass
class SynthResult:
    story_id: int
    request_sec: float = 0.0
    poll_sec: float = 0.0
    total_sec: float = 0.0
    success: bool = False
    error: str = ""


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def login_user(base_url, email, password):
    resp = requests.post(
        f"{base_url}/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Login failed for {email}: {resp.status_code} {resp.text[:200]}")
    data = resp.json()
    return data["access_token"], data["refresh_token"], data["user"]["id"]


def get_voices(base_url, token):
    resp = requests.get(
        f"{base_url}/voices",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if resp.status_code != 200:
        return []
    data = resp.json()
    return data if isinstance(data, list) else data.get("voices", [])


def upload_voice(base_url, token, voice_file_path, voice_name):
    with open(voice_file_path, "rb") as f:
        resp = requests.post(
            f"{base_url}/voices",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": (os.path.basename(voice_file_path), f, "audio/mpeg")},
            data={"name": voice_name},
            timeout=120,
        )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Voice upload failed: {resp.status_code} {resp.text[:300]}")
    return resp.json()


def get_voice(base_url, token, voice_id):
    resp = requests.get(
        f"{base_url}/voices/{voice_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if resp.status_code != 200:
        return None
    return resp.json()


def delete_voice(base_url, token, voice_id):
    resp = requests.delete(
        f"{base_url}/voices/{voice_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    return resp.status_code in (200, 204)


def get_stories(base_url, token):
    resp = requests.get(
        f"{base_url}/stories",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Get stories failed: {resp.status_code}")
    data = resp.json()
    return data if isinstance(data, list) else data.get("stories", [])


def request_synthesis(base_url, token, voice_id, story_id):
    resp = requests.post(
        f"{base_url}/voices/{voice_id}/stories/{story_id}/audio",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    if resp.status_code in (200, 202):
        return resp.status_code, resp.json()
    return resp.status_code, resp.text[:300]


def poll_audio(base_url, token, voice_id, story_id,
               timeout=POLL_TIMEOUT, interval=POLL_INTERVAL):
    start = time.monotonic()
    polls = 0
    while True:
        elapsed = time.monotonic() - start
        if elapsed >= timeout:
            return False, elapsed, polls, "timeout"
        resp = requests.head(
            f"{base_url}/voices/{voice_id}/stories/{story_id}/audio",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        polls += 1
        if resp.status_code == 200:
            return True, time.monotonic() - start, polls, "ready"
        if resp.status_code not in (404, 202, 401):
            logger.warning(
                "Unexpected HEAD status %d for voice=%d story=%d",
                resp.status_code, voice_id, story_id,
            )
        time.sleep(interval)


# ---------------------------------------------------------------------------
# Per-user test flow
# ---------------------------------------------------------------------------

def run_user_test(base_url, user_num, voice_file_path, stories, stories_per_user):
    result = UserResult(user_num=user_num)
    result.email = EMAIL_TEMPLATE.format(n=user_num)

    try:
        # 1. Login (user pre-created via setup_test_data.py)
        logger.info("[User %d] Logging in as %s", user_num, result.email)
        token, refresh_token, user_id = login_user(base_url, result.email, PASSWORD)
        result.user_id = user_id

        # 2. Delete any existing voices (fake ones from setup_test_data)
        existing_voices = get_voices(base_url, token)
        for v in existing_voices:
            vid = v.get("id")
            logger.info("[User %d] Deleting existing voice %d", user_num, vid)
            delete_voice(base_url, token, vid)

        # 3. Upload real voice sample
        logger.info("[User %d] Uploading voice sample %s", user_num, voice_file_path)
        t0 = time.monotonic()
        voice_data = upload_voice(
            base_url, token, voice_file_path,
            f"StressTest Voice {user_num}",
        )
        result.voice_upload_sec = time.monotonic() - t0
        result.voice_id = voice_data.get("id", 0)
        logger.info(
            "[User %d] Voice uploaded: id=%d status=%s (%.1fs)",
            user_num, result.voice_id,
            voice_data.get("status", voice_data.get("allocation_status", "?")),
            result.voice_upload_sec,
        )

        # 4. Wait for voice allocation (ElevenLabs/Cartesia clone)
        logger.info("[User %d] Waiting for voice allocation...", user_num)
        t0 = time.monotonic()
        voice_ready = False
        while time.monotonic() - t0 < VOICE_READY_TIMEOUT:
            voice_info = get_voice(base_url, token, result.voice_id)
            if voice_info:
                alloc = voice_info.get("allocation_status", "")
                status = voice_info.get("status", "")
                if alloc == "ready":
                    voice_ready = True
                    break
                if status == "error" or alloc == "error":
                    err_msg = voice_info.get("error_message", "unknown error")
                    raise RuntimeError(f"Voice allocation failed: {err_msg}")
            time.sleep(5)
        result.voice_ready_sec = time.monotonic() - t0

        if voice_ready:
            logger.info("[User %d] Voice ready in %.1fs", user_num, result.voice_ready_sec)
        else:
            logger.warning(
                "[User %d] Voice not ready after %.0fs, proceeding anyway",
                user_num, result.voice_ready_sec,
            )

        # 5. Request synthesis for selected stories
        selected_stories = stories[:stories_per_user]
        for story in selected_stories:
            story_id = story["id"]
            sr = SynthResult(story_id=story_id)

            logger.info(
                "[User %d] Requesting synthesis: story %d (%s)",
                user_num, story_id, story.get("title", "")[:30],
            )
            t0 = time.monotonic()
            status_code, resp_data = request_synthesis(base_url, token, result.voice_id, story_id)
            sr.request_sec = time.monotonic() - t0

            if status_code not in (200, 202):
                sr.error = f"Synthesis request failed: {status_code} {resp_data}"
                logger.error("[User %d] %s", user_num, sr.error)
                result.synth_results.append(sr)
                continue

            if (
                status_code == 200
                and isinstance(resp_data, dict)
                and resp_data.get("status") == "ready"
            ):
                sr.success = True
                sr.total_sec = sr.request_sec
                logger.info("[User %d] Story %d already ready", user_num, story_id)
                result.synth_results.append(sr)
                continue

            # 6. Poll until audio ready
            logger.info("[User %d] Polling for story %d audio...", user_num, story_id)
            t0 = time.monotonic()
            success, elapsed, polls, final_status = poll_audio(
                base_url, token, result.voice_id, story_id,
            )
            sr.poll_sec = elapsed
            sr.total_sec = sr.request_sec + sr.poll_sec
            sr.success = success

            if success:
                logger.info(
                    "[User %d] Story %d ready in %.1fs (%d polls)",
                    user_num, story_id, sr.total_sec, polls,
                )
            else:
                sr.error = f"Poll ended: {final_status}"
                logger.error(
                    "[User %d] Story %d failed: %s (%.1fs)",
                    user_num, story_id, final_status, sr.total_sec,
                )

            result.synth_results.append(sr)

    except Exception as exc:
        result.errors.append(str(exc))
        logger.error("[User %d] Fatal error: %s", user_num, exc)

    return result


# ---------------------------------------------------------------------------
# Cleanup helper
# ---------------------------------------------------------------------------

def cleanup_voices(base_url, num_users):
    """Delete all voices for stress test users (via API)."""
    cleaned = 0
    for n in range(1, num_users + 1):
        email = EMAIL_TEMPLATE.format(n=n)
        try:
            token, _, _ = login_user(base_url, email, PASSWORD)
            voices = get_voices(base_url, token)
            for v in voices:
                if delete_voice(base_url, token, v["id"]):
                    logger.info("Deleted voice %d for %s", v["id"], email)
                    cleaned += 1
        except Exception as exc:
            logger.warning("Cleanup failed for %s: %s", email, exc)
    logger.info("Cleaned up %d voices total", cleaned)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Production stress test with real voice cloning + synthesis",
    )
    parser.add_argument("--base-url", required=True, help="Production API base URL")
    parser.add_argument("--users", type=int, default=2, help="Concurrent users (default: 2)")
    parser.add_argument("--stories", type=int, default=1, help="Stories per user (default: 1)")
    parser.add_argument("--voice-file", default="001.mp3", help="Voice sample file")
    parser.add_argument("--cleanup-only", action="store_true", help="Only delete voices")
    args = parser.parse_args()

    voice_path = Path(args.voice_file)
    if not voice_path.exists():
        voice_path = Path(__file__).resolve().parent.parent.parent / args.voice_file
    if not args.cleanup_only and not voice_path.exists():
        logger.error("Voice file not found: %s", args.voice_file)
        sys.exit(1)

    if args.cleanup_only:
        logger.info("Cleaning up voices for %d stress test users...", args.users)
        cleanup_voices(args.base_url, args.users)
        return

    # Verify first user can login (users must be pre-created)
    logger.info("Verifying test users exist...")
    try:
        token, _, _ = login_user(args.base_url, EMAIL_TEMPLATE.format(n=1), PASSWORD)
    except RuntimeError as exc:
        logger.error(
            "Cannot login as test user. Run setup_test_data.py first:\n"
            "  render jobs create <service-id> "
            '--start-command "python -m tests.load.setup_test_data"\n'
            "Error: %s", exc,
        )
        sys.exit(1)

    # Get stories list
    stories = get_stories(args.base_url, token)
    if not stories:
        logger.error("No stories in database")
        sys.exit(1)
    logger.info("Found %d stories, using %d per user", len(stories), args.stories)

    # Run concurrent user tests
    logger.info(
        "Starting stress test: %d users x %d stories, voice=%s",
        args.users, args.stories, voice_path.name,
    )

    results = []
    start_time = time.monotonic()

    with ThreadPoolExecutor(max_workers=args.users, thread_name_prefix="user") as pool:
        futures = {
            pool.submit(
                run_user_test, args.base_url, n, str(voice_path), stories, args.stories,
            ): n
            for n in range(1, args.users + 1)
        }
        for future in as_completed(futures):
            user_num = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                logger.error("User %d thread failed: %s", user_num, exc)

    total_time = time.monotonic() - start_time

    # --- Summary ---
    print("\n" + "=" * 70)
    print("PRODUCTION STRESS TEST RESULTS")
    print("=" * 70)
    print(f"Duration:  {total_time:.1f}s")
    print(f"Users:     {len(results)}/{args.users}")

    upload_times = [r.voice_upload_sec for r in results if r.voice_upload_sec > 0]
    if upload_times:
        print(f"\nVoice Upload (S3 + API):")
        print(f"  avg={sum(upload_times)/len(upload_times):.1f}s  "
              f"min={min(upload_times):.1f}s  max={max(upload_times):.1f}s")

    ready_times = [r.voice_ready_sec for r in results if r.voice_ready_sec > 0]
    if ready_times:
        print(f"\nVoice Allocation (clone on ElevenLabs/Cartesia):")
        print(f"  avg={sum(ready_times)/len(ready_times):.1f}s  "
              f"min={min(ready_times):.1f}s  max={max(ready_times):.1f}s")

    total_synths = sum(len(r.synth_results) for r in results)
    successful_synths = sum(1 for r in results for s in r.synth_results if s.success)
    failed_synths = total_synths - successful_synths

    print(f"\nAudio Synthesis: {successful_synths}/{total_synths} succeeded")
    synth_times = [s.total_sec for r in results for s in r.synth_results if s.success]
    if synth_times:
        print(f"  avg={sum(synth_times)/len(synth_times):.1f}s  "
              f"min={min(synth_times):.1f}s  max={max(synth_times):.1f}s")

    if failed_synths > 0:
        print(f"\nFailed ({failed_synths}):")
        for r in results:
            for s in r.synth_results:
                if not s.success:
                    print(f"  User {r.user_num}, Story {s.story_id}: {s.error}")

    errors = [e for r in results for e in r.errors]
    if errors:
        print(f"\nFatal errors ({len(errors)}):")
        for e in errors:
            print(f"  {e}")

    print("=" * 70)

    # Cleanup voices (users stay for future tests)
    print("\nCleaning up voices...")
    for r in results:
        if r.voice_id:
            try:
                tok, _, _ = login_user(args.base_url, r.email, PASSWORD)
                delete_voice(args.base_url, tok, r.voice_id)
                logger.info("Deleted voice %d", r.voice_id)
            except Exception as exc:
                logger.warning("Cleanup voice %d failed: %s", r.voice_id, exc)

    print("Done.")
    sys.exit(0 if failed_synths == 0 else 1)


if __name__ == "__main__":
    main()
