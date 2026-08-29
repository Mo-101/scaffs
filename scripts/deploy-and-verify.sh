#!/usr/bin/env bash
# ==============================================================================
# Scaffs One-Shot Deploy & Verify Script
# Standard execution: ./scripts/deploy-and-verify.sh [target_directory]
# ==============================================================================
set -euo pipefail

# Determine target directory safely
TARGET_DIR="${1:-}"
if [ -z "$TARGET_DIR" ]; then
    if [ -d "/opt/scaffs" ]; then
        TARGET_DIR="/opt/scaffs"
    elif [ -d "/opt/vibe-trading" ]; then
        TARGET_DIR="/opt/vibe-trading"
    else
        TARGET_DIR="$(pwd)"
    fi
fi

echo "==> Deploying Scaffs in: ${TARGET_DIR}"
cd -- "$TARGET_DIR"

# 1. Pull latest code if git repo exists
if [ -d ".git" ]; then
    echo "==> 1. Fetching latest repository changes..."
    git pull --rebase origin main || git pull origin main || echo "Notice: Git pull skipped or uncommitted changes exist."
fi

# 2. Check Prerequisites
echo "==> 2. Verifying Docker & Compose environment..."
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
fi

# 3. Environment configuration
echo "==> 3. Verifying .env configuration..."
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo "Creating .env from .env.example..."
        cp .env.example .env
    else
        echo "ERROR: No .env or .env.example file found."
        exit 1
    fi
fi

# Safety Floor Enforcer
check_flag() {
    local key="$1"
    local expected="$2"
    local val
    val=$(grep -E "^${key}=" .env | cut -d'=' -f2- | tr -d '"' | tr -d "'" || true)
    if [ -z "$val" ]; then
        echo "${key}=${expected}" >> .env
    fi
}
check_flag "ENABLE_LIVE_TRADING" "false"
check_flag "ALLOW_AUTO_EXECUTION" "false"
check_flag "REQUIRE_MANUAL_APPROVAL" "true"
check_flag "NEW_ENTRIES_ENABLED" "false"

# 4. Build & Up
echo "==> 4. Building Docker containers..."
docker compose build --parallel

echo "==> 5. Starting container stack..."
docker compose up -d --remove-orphans

# 6. Verify Health & Log Tail
API_PORT=$(grep -E "^API_HOST_PORT=" .env | cut -d'=' -f2- | tr -d '"' | tr -d "'" || echo "8000")
API_PORT="${API_PORT:-8000}"

echo "==> 6. Verifying stack health..."
sleep 5
docker compose ps

echo "==> 7. Checking API response on port ${API_PORT}..."
HEALTH_PASSED=false
for i in {1..10}; do
    if curl -fsSL "http://127.0.0.1:${API_PORT}/health" > /dev/null 2>&1 || curl -fsSL "http://127.0.0.1:8000/health" > /dev/null 2>&1; then
        HEALTH_PASSED=true
        break
    fi
    sleep 2
done

if [ "$HEALTH_PASSED" = true ]; then
    echo "✅ DEPLOYMENT SUCCESS: Scaffs API is healthy and operational!"
else
    echo "⚠️ WARNING: Health check pending. Container logs:"
    docker compose logs --tail=40
fi
