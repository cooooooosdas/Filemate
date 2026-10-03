#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "请使用 root 运行：sudo bash deploy/bootstrap-ubuntu.sh" >&2
  exit 1
fi

if [[ ! -f deploy/.env.production ]]; then
  echo "缺少 deploy/.env.production，停止部署。" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  apt-get update
  if ! apt-get install -y docker.io docker-compose-v2 ca-certificates curl; then
    apt-get install -y docker.io docker-compose-plugin ca-certificates curl
  fi
fi

systemctl enable --now docker
docker compose version

cd deploy
docker compose --env-file .env.production up -d --build
docker compose ps

for attempt in {1..30}; do
  if docker compose exec -T api python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/api/health', timeout=5)"; then
    echo "FileMate API 健康检查通过。"
    exit 0
  fi
  sleep 2
done

docker compose logs --tail=120 api web
echo "FileMate API 健康检查超时。" >&2
exit 1
