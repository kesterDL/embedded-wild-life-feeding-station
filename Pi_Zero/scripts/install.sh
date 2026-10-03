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

echo "[1/5] Copying files to ${INSTALL_DIR}..."
mkdir -p "${INSTALL_DIR}/Pi_Zero"
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cp -r "${PROJECT_ROOT}/Pi_Zero/." "${INSTALL_DIR}/Pi_Zero/"


echo "[2/5] Preparing SD card Wild_Life_Recordings directory..."
RECORDINGS_DIR=""
if [ -d "/boot/firmware" ]; then
  RECORDINGS_DIR="/boot/firmware/Wild_Life_Recordings"
elif [ -d "/boot" ]; then
  RECORDINGS_DIR="/boot/Wild_Life_Recordings"
else
  RECORDINGS_DIR="/var/media/Wild_Life_Recordings"
fi

mkdir -p "${RECORDINGS_DIR}"
chmod 777 "${RECORDINGS_DIR}" || true

# Create symlink for standard user convenience if david exists
if id "david" &>/dev/null; then
  ln -sfn "${RECORDINGS_DIR}" /home/david/Wild_Life_Recordings
  chown -h david:david /home/david/Wild_Life_Recordings 2>/dev/null || true
fi

echo "[3/5] Ensuring MP4 muxer (ffmpeg or MP4Box) is installed for MP4 encapsulation..."
if ! command -v ffmpeg &>/dev/null && ! command -v MP4Box &>/dev/null; then
  apt-get update && (apt-get install -y --no-install-recommends ffmpeg || apt-get install -y --no-install-recommends gpac) || echo "Warning: Could not install ffmpeg/gpac. Raw .h264 fallback will be used."
fi


echo "[4/5] Installing systemd service..."
cp "${SERVICE_SRC}" "${SERVICE_DEST}"
chmod 644 "${SERVICE_DEST}"

echo "[5/5] Enabling service..."
systemctl daemon-reload
systemctl enable squirrel-record.service

echo "=== SquirrelFeeder service installed successfully! ==="
echo "Recordings directory ready at: ${RECORDINGS_DIR}"
echo "(Visible as 'Wild_Life_Recordings' when SD card is read on a Mac)"

