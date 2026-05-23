#!/bin/bash

set -e

cd /root/music_bot-main
git config --global --add safe.directory /root/music_bot-main
git pull
docker compose down --remove-orphans
docker compose -f docker-compose.prod.yml up -d --build
