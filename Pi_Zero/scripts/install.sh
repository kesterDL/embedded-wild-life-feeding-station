#!/bin/bash
# ==============================================================================
# SquirrelFeeder MVP: Deployment and Installation Script
# ==============================================================================

set -e

if [ "$EUID" -ne 0 ]; then
  echo "Error: Please run as root (sudo ./install.sh)"
  exit 1
fi

INSTALL_DIR="/opt/squirrelfeeder"
SERVICE_SRC="$(dirname "$0")/squirrel-record.service"
SERVICE_DEST="/etc/systemd/system/squirrel-record.service"

echo "=== Installing SquirrelFeeder Media Node ==="

echo "[1/4] Copying files to ${INSTALL_DIR}..."
mkdir -p "${INSTALL_DIR}"
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cp -r "${PROJECT_ROOT}/Pi_Zero" "${INSTALL_DIR}/"

echo "[2/4] Ensuring MP4Box (gpac) is installed for MP4 encapsulation..."
if ! command -v MP4Box &>/dev/null; then
  apt-get update && apt-get install -y --no-install-recommends gpac || echo "Warning: Could not install gpac. Raw .h264 fallback will be used."
fi

echo "[3/4] Installing systemd service..."
cp "${SERVICE_SRC}" "${SERVICE_DEST}"
chmod 644 "${SERVICE_DEST}"

echo "[4/4] Enabling service..."
systemctl daemon-reload
systemctl enable squirrel-record.service

echo "=== SquirrelFeeder service installed successfully! ==="
