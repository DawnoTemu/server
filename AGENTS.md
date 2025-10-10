# Repository Guidelines

## Project Structure & Module Organization
The Flask entrypoint lives in `app.py`, with blueprints registered from `routes/`. Domain logic stays in `controllers/`, SQLAlchemy models in `models/`, and asynchronous jobs in `tasks/`. Shared integrations (S3, email, voice providers) reside in `utils/`. Email templates live under `templates/`, while static assets and curated fairy tales are in `static/` and `stories/`. Database migrations are tracked in `migrations/`, and API artifacts are in `docs/`. The `tests/` tree mirrors runtime packages—place new tests beside the feature they cover.

## Build, Test, and Development Commands
Create an isolated environment with `python -m venv venv && source venv/bin/activate`, then install dependencies via `pip install -r requirements.txt`. Apply schema updates before running with `flask db upgrade`. Start the API using `flask run --host=0.0.0.0 --port=8000` and launch background processing through `celery -A celery_worker.celery_app worker --loglevel=info`; ensure `redis-server` is running locally first. Execute the suite with `pytest -v`; append `--cov=app` to inspect coverage during larger changes. Production deploys rely on `gunicorn app:app` and the Heroku `Procfile`.

## Coding Style & Naming Conventions
Follow PEP 8 with 4-space indentation and prefer type hints for new modules. Controllers, routes, and tasks use descriptive snake_case filenames (e.g., `voice_controller.py`, `audio_routes.py`). Keep configuration logic inside `config.py` and load secrets through environment variables—never hardcode credentials or API keys. Commit supporting utilities (scripts, fixtures) under the relevant folder so reviewers can trace feature boundaries easily.

## Testing Guidelines
Pytest is configured through `pytest.ini` to discover files named `test_*.py`, classes starting with `Test`, and functions named `test_*`. Reuse fixtures from `tests/fixtures` instead of calling external APIs; mock S3, Cartesia, and ElevenLabs clients with `pytest-mock` to keep runs deterministic. Add high-level endpoint checks in `tests/test_endpoints.py` when introducing new routes, and pair them with unit tests under the corresponding `test_*` subdirectory.

## Commit & Pull Request Guidelines
Use concise, descriptive commit subjects similar to the current history (e.g., `Sentry for Celery`). Keep each commit scoped to a single concern; split database migrations, API surface changes, and UI tweaks. Pull requests should summarize the change, list manual and automated test results (`pytest -v`, Celery worker smoke checks), and link the relevant tracking issue. Include screenshots or logs when adjusting admin flows or asynchronous jobs so reviewers can verify behaviour quickly.

## Configuration & Secrets
Create a `.env` file in the `server/` directory as described in `README.md`, supplying Cartesia, ElevenLabs, Resend, Redis, and AWS values. Never commit `.env`, voice samples, or generated audio; temporary artifacts belong in `uploads/` locally or S3 in production. When rotating keys, update environment variables in your deployment platform and confirm that both Flask and Celery processes restart with the new settings.
