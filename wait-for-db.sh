#!/bin/bash
# wait-for-db.sh
set -e
host="db"
port="5432"
cmd="make migrate run.server.prod"
until pg_isready -h "$host" -p "$port"; do
  >&2 echo "Postgres is unavailable - sleeping"
  sleep 1
done
>&2 echo "Postgres is up - executing command"
exec $cmd
