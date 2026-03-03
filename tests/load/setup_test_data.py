"""
Setup test data for local Docker load testing.

Creates test users (active, email-confirmed, with credits) directly via
the database, bypassing HTTP auth flows. Run inside the Docker network
where the app and database are available.

Usage:
  # From docker-compose:
  docker compose -f docker-compose.yml -f tests/load/docker-compose.loadtest.yml \
    run --rm web python -m tests.load.setup_test_data

  # Or inside a running container:
  python -m tests.load.setup_test_data
"""

import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("loadtest.setup")


def create_test_data():
    from app import app
    from database import db
    from models.user_model import User
    from models.voice_model import Voice, VoiceAllocationStatus, VoiceStatus
    from models.credit_model import grant
    from tests.load.config import TEST_USER_COUNT, TEST_USER_PASSWORD, TEST_USER_EMAIL_TEMPLATE

    with app.app_context():
        created = 0
        skipped = 0

        for n in range(1, TEST_USER_COUNT + 1):
            email = TEST_USER_EMAIL_TEMPLATE.format(n=n)
            existing = User.query.filter_by(email=email).first()
            if existing:
                # Ensure user has a voice
                _ensure_voice(db, existing)
                skipped += 1
                continue

            user = User(
                email=email,
                is_active=True,
                email_confirmed=True,
                is_admin=False,
                credits_balance=0,
            )
            user.set_password(TEST_USER_PASSWORD)
            db.session.add(user)
            db.session.flush()

            grant(user.id, 100, "loadtest_setup", "free")
            _ensure_voice(db, user)
            created += 1

        db.session.commit()
        logger.info(
            "Test users: %d created, %d already existed (total: %d)",
            created, skipped, TEST_USER_COUNT,
        )

        # Verify a sample user can be looked up
        sample_email = TEST_USER_EMAIL_TEMPLATE.format(n=1)
        sample = User.query.filter_by(email=sample_email).first()
        if sample:
            logger.info(
                "Verified: %s active=%s confirmed=%s balance=%s",
                sample.email, sample.is_active, sample.email_confirmed, sample.credits_balance,
            )
        else:
            logger.error("Could not find sample user %s", sample_email)
            return False

        # Seed stories if none exist
        from models.story_model import Story
        story_count = Story.query.count()
        if story_count == 0:
            logger.info("No stories found — seeding from stories_new/")
            _seed_stories(db)
            story_count = Story.query.count()

        logger.info("Stories in database: %d", story_count)
        return True


def _ensure_voice(db, user):
    """Ensure a user has at least one ready voice for load testing."""
    from models.voice_model import Voice, VoiceAllocationStatus, VoiceStatus

    existing = Voice.query.filter_by(user_id=user.id).first()
    if existing:
        return existing

    voice = Voice(
        name=f"Loadtest Voice ({user.email})",
        user_id=user.id,
        elevenlabs_voice_id=f"fake-loadtest-{user.id}",
        s3_sample_key=f"loadtest/voice_{user.id}.wav",
        status=VoiceStatus.READY,
        allocation_status=VoiceAllocationStatus.READY,
    )
    db.session.add(voice)
    db.session.flush()
    return voice


def _seed_stories(db):
    """Seed stories from stories_new/ JSON files into the database."""
    import json
    from pathlib import Path
    from models.story_model import Story

    stories_dir = Path(__file__).resolve().parent.parent.parent / "stories_new"
    if not stories_dir.exists():
        logger.warning("stories_new/ directory not found at %s", stories_dir)
        return

    count = 0
    for fp in sorted(stories_dir.glob("*.json")):
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)

        existing = Story.query.filter_by(title=data.get("title", "")).first()
        if existing:
            continue

        story = Story(
            title=data.get("title", "Untitled"),
            author=data.get("author", "Unknown"),
            description=data.get("description", ""),
            content=data.get("content", ""),
            cover_filename=data.get("cover_filename"),
        )
        db.session.add(story)
        count += 1

    db.session.commit()
    logger.info("Seeded %d stories from %s", count, stories_dir)


def cleanup_test_data():
    """Remove all load test users and their associated data."""
    from app import app
    from database import db
    from models.user_model import User
    from tests.load.config import TEST_USER_COUNT, TEST_USER_EMAIL_TEMPLATE

    with app.app_context():
        deleted = 0
        for n in range(1, TEST_USER_COUNT + 1):
            email = TEST_USER_EMAIL_TEMPLATE.format(n=n)
            user = User.query.filter_by(email=email).first()
            if user:
                db.session.delete(user)
                deleted += 1
        db.session.commit()
        logger.info("Cleaned up %d test users", deleted)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "cleanup":
        cleanup_test_data()
    else:
        ok = create_test_data()
        sys.exit(0 if ok else 1)
