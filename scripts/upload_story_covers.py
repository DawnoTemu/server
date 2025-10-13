import json
import mimetypes
import os
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv


def load_environment() -> None:
    """Load environment variables, preferring Docker-specific settings."""
    for candidate in (".env.docker", ".env"):
        env_path = Path(candidate)
        if env_path.exists():
            load_dotenv(env_path)


def get_s3_client():
    """Initialise an S3 client honouring local MinIO overrides."""
    region = os.getenv("AWS_REGION", "us-east-1")
    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    endpoint_url = os.getenv("AWS_S3_ENDPOINT_URL")
    use_ssl = os.getenv("AWS_S3_USE_SSL", "true").lower() in ("1", "true", "yes")
    addressing_style = os.getenv("AWS_S3_ADDRESSING_STYLE")

    config_kwargs = {"retries": {"max_attempts": 5, "mode": "adaptive"}}
    if addressing_style:
        config_kwargs["s3"] = {"addressing_style": addressing_style}

    return boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        endpoint_url=endpoint_url,
        use_ssl=use_ssl,
        config=Config(**config_kwargs),
    )


def ensure_bucket(client, bucket: str) -> None:
    """Create the bucket if it does not already exist."""
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as exc:
        error_code = int(exc.response.get("Error", {}).get("Code", 0))
        if error_code == 404:
            client.create_bucket(Bucket=bucket)
        elif error_code == 403:
            raise RuntimeError(f"Access denied when checking bucket '{bucket}'") from exc
        else:
            raise


def discover_cover_files() -> list[tuple[dict, Path]]:
    """Yield story metadata along with the matching local cover path."""
    stories_dir = Path("stories_backup")
    images_dir = stories_dir / "images"

    if not stories_dir.exists():
        raise FileNotFoundError("stories_backup directory not found; nothing to upload.")

    results: list[tuple[dict, Path]] = []
    for story_file in sorted(stories_dir.glob("story_*.json")):
        try:
            with story_file.open("r", encoding="utf-8") as fh:
                story = json.load(fh)
        except json.JSONDecodeError as exc:
            print(f"Skipping {story_file}: invalid JSON ({exc})")
            continue

        key = story.get("s3_cover_key")
        cover_filename = story.get("cover_filename")
        story_id = story.get("id")

        if not key or not cover_filename or story_id is None:
            continue

        suffix = Path(cover_filename).suffix
        local_name = f"story_{story_id}_cover{suffix}"
        local_path = images_dir / local_name

        if not local_path.exists():
            print(f"Skipping story #{story_id}: cover file {local_path} not found.")
            continue

        results.append((story, local_path))

    return results


def upload_covers():
    load_environment()
    bucket = os.getenv("S3_BUCKET_NAME")
    if not bucket:
        raise RuntimeError("S3_BUCKET_NAME must be set to upload covers.")

    client = get_s3_client()
    ensure_bucket(client, bucket)

    uploads = discover_cover_files()
    if not uploads:
        print("No cover files discovered; nothing to upload.")
        return

    for story, local_path in uploads:
        key = story["s3_cover_key"]
        content_type = mimetypes.guess_type(local_path.name)[0] or "application/octet-stream"
        with local_path.open("rb") as data:
            client.upload_fileobj(
                data,
                bucket,
                key,
                ExtraArgs={
                    "ACL": "private",
                    "ContentType": content_type,
                },
            )
        print(f"Uploaded cover for story #{story['id']} to {bucket}/{key}")


if __name__ == "__main__":
    upload_covers()
