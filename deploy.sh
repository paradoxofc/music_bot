#!/bin/bash
# Деплой на VPS. Роли:
#   data — PostgreSQL + Redis (секрет SSH_HOST в GitHub Actions)
#   bot  — только Telegram-бот (секрет SSH_HOST2)
#   full — всё на одном сервере (локально / тест)
#
# Примеры:
#   bash deploy.sh data
#   bash deploy.sh bot
#   DEPLOY_ROLE=bot bash deploy.sh

set -euo pipefail

ROLE="${DEPLOY_ROLE:-${1:-bot}}"
REPO_DIR="${DEPLOY_DIR:-/root/music_bot-main}"

case "$ROLE" in
  data)
    COMPOSE_FILE="docker-compose.prod.data.yml"
    ;;
  bot)
    COMPOSE_FILE="docker-compose.prod.bot.yml"
    ;;
  full)
    COMPOSE_FILE="docker-compose.prod.yml"
    ;;
  *)
    echo "Неизвестная роль: $ROLE (data | bot | full)" >&2
    exit 1
    ;;
esac

cd "$REPO_DIR"
git config --global --add safe.directory "$REPO_DIR" 2>/dev/null || true
git fetch origin
git checkout main 2>/dev/null || git checkout master
git pull --ff-only

docker compose -f "$COMPOSE_FILE" down --remove-orphans
docker compose -f "$COMPOSE_FILE" up -d --build

echo "Deploy OK: role=$ROLE compose=$COMPOSE_FILE"
