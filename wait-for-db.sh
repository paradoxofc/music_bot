#!/bin/bash
# Ожидает готовности PostgreSQL и запускает бота.
set -e
host="${POSTGRES_HOST:-db}"
port="${POSTGRES_PORT:-5432}"

if ! getent hosts "$host" >/dev/null 2>&1; then
  >&2 echo "ERROR: host '$host' not found in Docker DNS."
  >&2 echo "Ensure 'db' service is Up and bot is on the same compose network (not /etc/hosts)."
  >&2 echo "Run: docker compose -f docker-compose.prod.yml ps"
  exit 1
fi

until pg_isready -h "$host" -p "$port"; do
  >&2 echo "Postgres is unavailable - sleeping"
  sleep 1
done

>&2 echo "Postgres is up - starting bot"
exec make run.bot
