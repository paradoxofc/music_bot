#!/usr/bin/env bash
# Поднимает чистые db/redis, прогоняет pytest, удаляет контейнеры и сети.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE_FILE="docker-compose.test.yml"

compose() {
  docker compose -f "$COMPOSE_FILE" "$@"
}

compose down -v --remove-orphans 2>/dev/null || true

compose up --build --abort-on-container-exit --exit-code-from test test
exit_code=$?

compose down -v --remove-orphans

exit "$exit_code"
