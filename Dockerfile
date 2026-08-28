# syntax=docker/dockerfile:1
FROM python:3.12-slim AS python-base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    curl \
    build-essential \
    libpq-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/agent/requirements.txt /app/backend/agent/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/agent/requirements.txt

COPY migrations /app/migrations
COPY backend/agent /app/backend/agent
COPY .env.example /app/.env.example

FROM node:20-slim AS frontend

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM python-base AS final

COPY --from=frontend /app/frontend/dist /app/frontend/dist
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

WORKDIR /app/backend/agent

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
