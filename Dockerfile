ARG PYTHON_VERSION=3.13

FROM python:${PYTHON_VERSION}-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential libpq-dev ffmpeg && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=app.py \
    PATH="/home/app/.local/bin:${PATH}"

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 ffmpeg netcat-openbsd && \
    rm -rf /var/lib/apt/lists/* && \
    useradd --create-home --shell /bin/bash app

COPY --from=builder /install /usr/local

COPY . /app

RUN chmod +x docker/entrypoint.sh && \
    chown -R app:app /app

USER app

EXPOSE 8000

ENTRYPOINT ["./docker/entrypoint.sh"]
