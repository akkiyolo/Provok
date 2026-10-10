# syntax=docker/dockerfile:1.7
# Provok API / worker image. Same image, different command:
#   API:    uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
#   Worker: arq backend.app.workers.main.WorkerSettings

FROM python:3.12-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt /tmp/requirements.txt
RUN python -m venv /opt/venv && /opt/venv/bin/pip install -r /tmp/requirements.txt

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/opt/venv/bin:$PATH" APP_ENV=production
# ffmpeg: highlight clips; curl: container healthcheck; tini: proper signal handling / zombie reaping
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl tini \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system provok && useradd --system --gid provok --home /app --shell /usr/sbin/nologin provok
WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY --chown=provok:provok backend /app/backend
USER provok
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD curl -fsS http://localhost:8000/health || exit 1
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", \
     "--forwarded-allow-ips", "*", "--timeout-graceful-shutdown", "20", "--no-server-header"]
