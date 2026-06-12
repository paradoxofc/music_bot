#!/usr/bin/env bash
# Первичная настройка VPS (запускать один раз от root).
# Использование:
#   export REPO_URL=https://github.com/USER/music_bot.git
#   export DEPLOY_ROLE=data   # или bot
#   bash scripts/server-bootstrap.sh
set -euo pipefail

REPO_URL="${REPO_URL:?Задайте REPO_URL (https://github.com/.../.git)}"
DEPLOY_ROLE="${DEPLOY_ROLE:?Задайте DEPLOY_ROLE: data или bot}"
INSTALL_DIR="${INSTALL_DIR:-/root/music_bot-main}"

apt-get update
apt-get install -y git docker.io docker-compose-plugin
systemctl enable --now docker

if [ ! -d "$INSTALL_DIR/.git" ]; then
  git clone "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Создан $INSTALL_DIR/.env — заполните секреты перед деплоем."
fi

chmod +x deploy.sh wait-for-db.sh
bash deploy.sh "$DEPLOY_ROLE"

echo "Bootstrap OK: role=$DEPLOY_ROLE dir=$INSTALL_DIR"
