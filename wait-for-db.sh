#!/bin/bash
# Ожидает готовности PostgreSQL и запускает бота.
set -e
host="${POSTGRES_HOST:-db}"
port="${POSTGRES_PORT:-5432}"

if [ "$host" != "127.0.0.1" ] && [ "$host" != "localhost" ]; then
  if ! getent hosts "$host" >/dev/null 2>&1; then
    >&2 echo "INFO: host '$host' not found in DNS, falling back to 127.0.0.1 (host network mode)"
    host="127.0.0.1"
  fi
fi

until pg_isready -h "$host" -p "$port"; do
  >&2 echo "Postgres is unavailable - sleeping"
  sleep 1
done

>&2 echo "Postgres is up - starting bot"
exec make run.bot
