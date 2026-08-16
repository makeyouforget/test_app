FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY . .

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/* \
    && python -m venv /app/.venv \
    && /app/.venv/bin/python -m pip install --upgrade pip \
    && /app/.venv/bin/pip install -r requirements.txt \
    && chmod +x /app/scripts/*.py /app/scripts/*.sh

FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000

RUN apt-get update && apt-get install -y --no-install-recommends \
        tini \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --home-dir /home/app --create-home --no-log-init app

WORKDIR /app

COPY --from=builder --chown=app:app /app /app

USER app

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 \
    CMD ["python", "/app/scripts/healthcheck.py"]

ENTRYPOINT ["/usr/bin/tini", "--", "/app/scripts/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]