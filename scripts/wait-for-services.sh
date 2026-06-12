#!/usr/bin/env bash
set -euo pipefail

host="${POSTGRES_HOST:-db}"
port="${POSTGRES_PORT:-5432}"
user="${POSTGRES_USER:-test}"

until pg_isready -h "$host" -p "$port" -U "$user"; do
  echo "Postgres is unavailable - sleeping" >&2
  sleep 1
done

echo "Postgres is up - running: $*" >&2
exec "$@"
