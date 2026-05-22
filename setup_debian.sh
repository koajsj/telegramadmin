#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Please run as root or with sudo."
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="tgadmin"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
VENV_DIR="${ROOT_DIR}/.venv"

if ! command -v python3 >/dev/null 2>&1; then
  apt-get update
  apt-get install -y python3 python3-pip python3-venv
fi

if ! python3 -m venv --help >/dev/null 2>&1; then
  apt-get update
  apt-get install -y python3-venv
fi

if [[ ! -f "${ROOT_DIR}/requirements.txt" ]]; then
  echo "requirements.txt not found in ${ROOT_DIR}"
  exit 1
fi

BOT_TOKEN="${BOT_TOKEN:-}"
if [[ -z "${BOT_TOKEN}" ]]; then
  read -r -p "Telegram bot token: " BOT_TOKEN
fi
if [[ -z "${BOT_TOKEN}" ]]; then
  echo "BOT_TOKEN is required."
  exit 1
fi

cat > "${ROOT_DIR}/.env" <<EOF
BOT_TOKEN=${BOT_TOKEN}
ACTION=mute
AUTO_LOAD_TXT=true
LEARNING_ENABLED=true
RULE_ENABLE_USERNAME=true
EOF

python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/python" -m pip install --upgrade pip
"${VENV_DIR}/bin/python" -m pip install -r "${ROOT_DIR}/requirements.txt"

cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=Telegram moderation bot
After=network.target

[Service]
Type=simple
WorkingDirectory=${ROOT_DIR}
ExecStart=${VENV_DIR}/bin/python ${ROOT_DIR}/main.py
Restart=always
EnvironmentFile=${ROOT_DIR}/.env

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}"
systemctl status "${SERVICE_NAME}" --no-pager

echo "Done. You can now chat with the bot privately and use /admin."
