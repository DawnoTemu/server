# Task & Context
Plan the migration of the Flask + Celery storytelling service to a Docker-based environment that supports local development and production-aligned workflows (web API, Celery worker, Postgres, Redis, optional S3 emulation) without altering application logic yet.

## Current State (codebase scan)
- `app.py`, `config.py`, `database.py` bootstrap Flask, SQLAlchemy, Celery integration, and rely on `.env`-driven settings; the project currently assumes native Python tooling.
- `celery_worker.py` and `tasks/__init__.py` expect Redis at `REDIS_URL` and share code with the web app; background jobs are orchestrated via the Procfile (`worker`) and Celery beat artifacts (`celerybeat-schedule`).
- Persistence lives in `migrations/`, `models/`, and external Postgres defined by `DATABASE_URL`; local development likely uses a manually managed database.
- Dependencies are locked in `requirements.txt`; deployment hints point to Python 3.10.13 (`runtime.txt`) while the README advertises Python 3.13, indicating a version mismatch to reconcile.
- Static/user data lives under `uploads/`, `stories/`, `static/`; `.env`, `.venv`, and other local artifacts exist in the repo but there is no `.dockerignore`.
- Documentation (`README.md`, `docs/`) covers manual setup only; no Dockerfile, compose stack, or container entrypoints are present.

## Proposed Changes (files & functions)
- Add a Docker build context (likely single `Dockerfile` reused for web and worker) that installs `requirements.txt`, sets up `gunicorn`/Celery entrypoints, exposes port 8000, and bakes in environment defaults.
- Introduce `docker-compose.yml` (or `compose.yaml`) defining services for `web`, `celery-worker`, optional `celery-beat`, `postgres`, `redis`, and potentially `minio`/`localstack` for S3; wire shared volumes for code reload and persistent data.
- Create `.dockerignore` to skip virtualenvs, local caches, test artifacts, `uploads`, and other unnecessary build context files.
- Add container entrypoint script(s) (e.g., `docker/entrypoint.sh`) to apply migrations (`flask db upgrade`), seed data if needed, and start the correct process (web vs worker).
- Provide a Docker-specific env template (e.g., `.env.docker.example`) listing required variables and local-safe defaults (`DATABASE_URL=postgresql+psycopg://postgres:postgres@db:5432/dawnotemu`, `REDIS_URL=redis://redis:6379/0`, etc.).
- Update `README.md` (and possibly `docs/`) with container usage instructions, networking notes, and troubleshooting tips; document how to run Celery worker, tests, and migrations within containers.
- Consider minor config tweaks (e.g., ensure `Config.SQLALCHEMY_DATABASE_URI` respects container hostnames, confirm `HOST`/`PORT` env usage) if assumptions about localhost need adjustment.

## Step-by-Step Plan
- Inventory required environment variables and craft `.env.docker.example`, noting secrets that must be supplied manually; decide on sane local defaults for S3 and email integrations.
- Draft `.dockerignore` to keep builds lightweight (exclude `.venv`, `uploads`, caches, large media, local logs).
- Implement multi-stage `Dockerfile` (base builder + runtime) that installs system deps (e.g., `build-essential`, `libpq-dev`), pip installs requirements, copies the app, and defines entry commands for web/worker.
- Create `docker-compose.yml` with service definitions, networks, volumes, healthchecks, and environment injection from `.env`/overrides; configure Postgres and Redis containers with persistent volumes.
- Add entrypoint/command scripts to run migrations before launching `gunicorn` or the Celery worker; mount shared code volume for dev auto-reload where helpful.
- Update documentation with clear instructions for building/running containers, executing migrations/tests inside the stack, and mapping ports/storage; call out optional services (Celery beat, MinIO).
- Validate by running `docker compose up`, ensuring the app starts, migrations apply, Celery connects, and local endpoints respond; capture follow-up tasks for CI integration if needed.

## Risks & Assumptions
- Docker base image must target the desired Python version; the README/runtime mismatch needs resolution during implementation.
- AWS S3, Cartesia, and ElevenLabs integrations may require real credentials; assume local development can disable or stub them or use MinIO/localstack.
- Running `flask db upgrade` inside containers depends on proper volume ordering and service readiness; may need wait-for scripts.
- Celery beat usage is unclear—adding it blindly could duplicate scheduling; will confirm necessity before adding.
- Large media directories (`uploads`, `stories`) might need host volumes to persist; ensure they are excluded from build context but mounted at runtime.
- Network access is restricted in the execution environment; the Docker plan must account for offline installs (e.g., mirrors) if necessary.

## Validation & Done Criteria
- Docker image builds successfully and runs both the Flask API (serving on port 8000) and Celery worker using shared configuration.
- `docker compose up` brings up Postgres and Redis, applies migrations automatically or via documented command, and the app connects to `db`/`redis` hostnames.
- Application endpoints and Celery tasks function in the containerized setup; logs confirm worker consumption without connection errors.
- Documentation includes end-to-end Docker usage, covering environment setup, migrations, running tests (`docker compose run web pytest -v`), and cleanup.
- New tooling files (`Dockerfile`, compose stack, `.dockerignore`, entrypoints) align with repo conventions and pass linting/formatting checks where applicable.

## Open Questions
- Should we include Celery beat and/or Flower in the default compose stack, or leave them as optional profiles?
Include Celery beat and Flower
- Do we need a local S3 emulator (MinIO/localstack), or will developers rely on real AWS credentials when testing audio flows?
Use local S3 emulator
- Should the Docker image target Python 3.10 (per `runtime.txt`) or upgrade to 3.13 as advertised—are there compatibility constraints?
Use Python 3.13 (slim base image)
- Are there CI/CD expectations (e.g., GitHub Actions) that should adopt the container image immediately, or is this phase limited to local workflows?
No
