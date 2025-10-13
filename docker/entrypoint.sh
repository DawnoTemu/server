#!/usr/bin/env bash
set -euo pipefail

SERVICE="${1:-web}"

export FLASK_APP=${FLASK_APP:=app.py}
export PYTHONPATH=/app

wait_for_service() {
  local name="$1"
  local host="$2"
  local port="$3"

  for _ in $(seq 1 30); do
    if nc -z "$host" "$port" >/dev/null 2>&1; then
      return 0
    fi
    echo "Waiting for ${name} at ${host}:${port}..."
    sleep 2
  done

  echo "Timed out waiting for ${name} at ${host}:${port}" >&2
  exit 1
}

parse_host() {
  local url="$1"
  local default_host="$2"
  local stripped="${url#*://}"
  stripped="${stripped%%/*}"
  if [[ "$stripped" == *@* ]]; then
    stripped="${stripped##*@}"
  fi
  local host="${stripped%%:*}"
  echo "${host:-$default_host}"
}

parse_port() {
  local url="$1"
  local default_port="$2"
  local stripped="${url#*://}"
  stripped="${stripped%%/*}"
  if [[ "$stripped" == *@* ]]; then
    stripped="${stripped##*@}"
  fi
  local port="${stripped##*:}"
  if [[ "$stripped" == "$port" ]]; then
    echo "$default_port"
  else
    echo "$port"
  fi
}

case "${SERVICE}" in
  web)
    if [[ -n "${DATABASE_URL:-}" ]]; then
      DB_HOST=$(parse_host "${DATABASE_URL}" "db")
      DB_PORT=$(parse_port "${DATABASE_URL}" "5432")
      wait_for_service "Postgres" "${DB_HOST:-db}" "${DB_PORT:-5432}"
    fi

    if [[ -n "${REDIS_URL:-}" ]]; then
      REDIS_HOST=$(parse_host "${REDIS_URL}" "redis")
      REDIS_PORT=$(parse_port "${REDIS_URL}" "6379")
      wait_for_service "Redis" "${REDIS_HOST:-redis}" "${REDIS_PORT:-6379}"
    fi

    if [[ -n "${AWS_S3_ENDPOINT_URL:-}" ]]; then
      S3_HOST=$(parse_host "${AWS_S3_ENDPOINT_URL}" "minio")
      S3_PORT=$(parse_port "${AWS_S3_ENDPOINT_URL}" "9000")
      wait_for_service "Object storage" "${S3_HOST:-minio}" "${S3_PORT:-9000}"
    fi

    flask db upgrade
    exec gunicorn app:app --bind 0.0.0.0:${PORT:-8000} --timeout 240 --workers ${WEB_CONCURRENCY:-2} --preload
    ;;
  flask-reload)
    if [[ -n "${DATABASE_URL:-}" ]]; then
      DB_HOST=$(parse_host "${DATABASE_URL}" "db")
      DB_PORT=$(parse_port "${DATABASE_URL}" "5432")
      wait_for_service "Postgres" "${DB_HOST:-db}" "${DB_PORT:-5432}"
    fi

    if [[ -n "${REDIS_URL:-}" ]]; then
      REDIS_HOST=$(parse_host "${REDIS_URL}" "redis")
      REDIS_PORT=$(parse_port "${REDIS_URL}" "6379")
      wait_for_service "Redis" "${REDIS_HOST:-redis}" "${REDIS_PORT:-6379}"
    fi

    if [[ -n "${AWS_S3_ENDPOINT_URL:-}" ]]; then
      S3_HOST=$(parse_host "${AWS_S3_ENDPOINT_URL}" "minio")
      S3_PORT=$(parse_port "${AWS_S3_ENDPOINT_URL}" "9000")
      wait_for_service "Object storage" "${S3_HOST:-minio}" "${S3_PORT:-9000}"
    fi

    flask db upgrade
    exec flask run --host 0.0.0.0 --port "${PORT:-8000}" --reload
    ;;
  worker)
    if [[ -n "${REDIS_URL:-}" ]]; then
      REDIS_HOST=$(parse_host "${REDIS_URL}" "redis")
      REDIS_PORT=$(parse_port "${REDIS_URL}" "6379")
    fi
    wait_for_service "Redis" "${REDIS_HOST:-redis}" "${REDIS_PORT:-6379}"
    if [[ -n "${AWS_S3_ENDPOINT_URL:-}" ]]; then
      S3_HOST=$(parse_host "${AWS_S3_ENDPOINT_URL}" "minio")
      S3_PORT=$(parse_port "${AWS_S3_ENDPOINT_URL}" "9000")
      wait_for_service "Object storage" "${S3_HOST:-minio}" "${S3_PORT:-9000}"
    fi
    exec celery -A celery_worker.celery_app worker --loglevel="${CELERY_LOG_LEVEL:-info}"
    ;;
  beat)
    if [[ -n "${REDIS_URL:-}" ]]; then
      REDIS_HOST=$(parse_host "${REDIS_URL}" "redis")
      REDIS_PORT=$(parse_port "${REDIS_URL}" "6379")
    fi
    wait_for_service "Redis" "${REDIS_HOST:-redis}" "${REDIS_PORT:-6379}"
    if [[ -n "${AWS_S3_ENDPOINT_URL:-}" ]]; then
      S3_HOST=$(parse_host "${AWS_S3_ENDPOINT_URL}" "minio")
      S3_PORT=$(parse_port "${AWS_S3_ENDPOINT_URL}" "9000")
      wait_for_service "Object storage" "${S3_HOST:-minio}" "${S3_PORT:-9000}"
    fi
    exec celery -A celery_worker.celery_app beat --loglevel="${CELERY_LOG_LEVEL:-info}"
    ;;
  *)
    exec "$@"
    ;;
esac
