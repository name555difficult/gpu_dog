#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/mnt/ssd1t/gpu_dog}"
SERVICE_NAME="${SERVICE_NAME:-gpu-monitor.service}"
SERVICE_SRC="${PROJECT_DIR}/systemd/${SERVICE_NAME}"
SERVICE_DST="/etc/systemd/system/${SERVICE_NAME}"

if [[ ! -f "${SERVICE_SRC}" ]]; then
  echo "service file not found: ${SERVICE_SRC}" >&2
  exit 1
fi

if ! command -v systemctl >/dev/null 2>&1; then
  echo "systemctl not found; this host may not use systemd" >&2
  exit 1
fi

if command -v systemd-analyze >/dev/null 2>&1; then
  systemd-analyze verify "${SERVICE_SRC}"
fi

sudo install -m 0644 "${SERVICE_SRC}" "${SERVICE_DST}"
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"
sudo systemctl restart "${SERVICE_NAME}"
sudo systemctl status "${SERVICE_NAME}" --no-pager
