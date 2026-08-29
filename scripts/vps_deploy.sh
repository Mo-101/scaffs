#!/usr/bin/env bash
# ==============================================================================
# Scaffs VPS Production Deployment Script
# Target Host: 31.97.180.251 | Target Path: /opt/scaffs (or /opt/vibe-trading)
# ==============================================================================
set -euo pipefail

DEPLOY_DIR="${1:-}"
if [ -z "$DEPLOY_DIR" ]; then
    if [ -d "/opt/scaffs" ]; then
        DEPLOY_DIR="/opt/scaffs"
    elif [ -d "/opt/vibe-trading" ]; then
        DEPLOY_DIR="/opt/vibe-trading"
    else
        DEPLOY_DIR="$(pwd)"
    fi
fi
if [ -d "$DEPLOY_DIR" ]; then
    cd "$DEPLOY_DIR"
fi

echo "==> 1. Checking Prerequisites (Docker & Docker Compose)..."
if ! command -v docker &> /dev/null; then
    echo "Docker is not installed. Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$USER"
fi

if ! docker compose version &> /dev/null; then
    echo "Docker Compose plugin missing. Installing docker-compose-plugin..."
    sudo apt-get update && sudo apt-get install -y docker-compose-plugin
fi

echo "==> 2. Verifying Production Environment Configuration (.env)..."
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo "Creating .env from .env.example..."
        cp .env.example .env
        echo "Created .env template. Please review credentials before continuing."
    else
        echo "Error: No .env or .env.example found in $PWD."
        exit 1
    fi
fi

# Ensure critical safety/governance floor flags are locked in .env
echo "==> 3. Verifying Governance Safety Floor..."
check_flag() {
    local key="$1"
    local expected="$2"
    local val
    val=$(grep -E "^${key}=" .env | cut -d'=' -f2- | tr -d '"' | tr -d "'" || true)
    if [ -z "$val" ]; then
        echo "Appending default safety flag ${key}=${expected} to .env..."
        echo "${key}=${expected}" >> .env
    elif [ "$val" != "$expected" ]; then
        echo "WARNING: ${key} is currently set to '${val}' (expected '${expected}' for safety)."
    fi
}

check_flag "ENABLE_LIVE_TRADING" "false"
check_flag "ALLOW_AUTO_EXECUTION" "false"
check_flag "REQUIRE_MANUAL_APPROVAL" "true"
check_flag "NEW_ENTRIES_ENABLED" "false"

# Resolve port configuration (default to 8899 on sovereign VPS)
API_PORT=$(grep -E "^API_HOST_PORT=" .env | cut -d'=' -f2- | tr -d '"' | tr -d "'" || echo "8899")
API_PORT="${API_PORT:-8899}"

echo "==> 4. Building Multi-stage Docker Container Images..."
# Note: Existing postgres_data volume is preserved intact; migrations in docker-entrypoint.sh are idempotent.
docker compose build --parallel

echo "==> 5. Starting Container Services (Preserving Postgres Volume)..."
docker compose up -d --remove-orphans

echo "==> 6. Verifying Deployment Health..."
sleep 5
docker compose ps

echo "==> 7. Testing Local API Health Endpoint (Port ${API_PORT})..."
if curl -fsSL "http://127.0.0.1:${API_PORT}/health" > /dev/null 2>&1; then
    echo "SUCCESS: Scaffs API is live and responding on http://127.0.0.1:${API_PORT}!"
elif curl -fsSL "http://127.0.0.1:8000/health" > /dev/null 2>&1; then
    echo "SUCCESS: Scaffs API is live and responding on http://127.0.0.1:8000!"
else
    echo "WARNING: Health check did not respond immediately. Inspecting container logs..."
    docker compose logs --tail=40
fi
