# syntax=docker/dockerfile:1
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# Dependencies first: this layer is cached across code changes, which is most
# of the difference between a 15-second and a 3-minute cloud build.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Run unprivileged. A container that does not need root should not have it.
RUN useradd --create-home --uid 10001 pharma
USER pharma

EXPOSE 8080
ENV PORT=8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import os,urllib.request;urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/healthz')"

# Shell form so $PORT is expanded at runtime by the platform that injects it.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
