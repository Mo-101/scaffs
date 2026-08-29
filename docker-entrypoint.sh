#!/bin/bash
set -eo pipefail

cd /app/backend/agent

PGHOST="${POSTGRES_HOST:-postgres}"
PGPORT="${POSTGRES_PORT:-5432}"
PGUSER="${POSTGRES_USER:-postgres}"
PGPASSWORD="${POSTGRES_PASSWORD:-mostar}"
PGDB="${POSTGRES_DB:-mostar}"

# Wait for Postgres
for i in $(seq 1 30); do
  if pg_isready -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

# Apply migrations
if [ -d /app/migrations ]; then
  for f in $(ls /app/migrations/*.sql | sort); do
    [ -f "$f" ] || continue
    echo "[migration] Applying $f..."
    PGPASSWORD="$PGPASSWORD" psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDB" -f "$f" || true
  done
fi

# Override psycopg to use the docker network database
export VIBE_PAPER_DATABASE_URL="host=$PGHOST dbname=$PGDB port=$PGPORT user=$PGUSER password=$PGPASSWORD"
export DATABASE_URL="postgresql://${PGUSER}:${PGPASSWORD}@${PGHOST}:${PGPORT}/${PGDB}"

case "$1" in
  api)
    exec python api_server.py --host 0.0.0.0 --port 8000
    ;;
  worker)
    exec python start_all_services.py
    ;;
  *)
    exec "$@"
    ;;
esac
