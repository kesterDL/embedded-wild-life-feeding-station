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

echo "[1/3] Copying files to ${INSTALL_DIR}..."
mkdir -p "${INSTALL_DIR}"
cp -r "$(dirname "$0")/../.." "${INSTALL_DIR}/" 2>/dev/null || true

echo "[2/3] Installing systemd service..."
cp "${SERVICE_SRC}" "${SERVICE_DEST}"
chmod 644 "${SERVICE_DEST}"

echo "[3/3] Enabling service..."
systemctl daemon-reload
systemctl enable squirrel-record.service

echo "=== SquirrelFeeder service installed successfully! ==="
