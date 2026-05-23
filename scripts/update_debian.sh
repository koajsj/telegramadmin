#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "请使用 sudo 运行: sudo bash scripts/update_debian.sh"
  exit 1
fi

cd "${ROOT_DIR}"

git fetch --all --prune
git pull --ff-only

docker compose up -d --build
docker compose exec -T bot alembic upgrade head

echo "更新完成。"
echo "查看日志: docker compose logs -f bot"
