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


echo "[2/5] Preparing ext4 Wild_Life_Recordings directory..."
TARGET_USER="${SUDO_USER:-$(logname 2>/dev/null || echo "$USER")}"
if [ -n "$TARGET_USER" ] && [ "$TARGET_USER" != "root" ] && [ -d "/home/${TARGET_USER}" ]; then
  RECORDINGS_DIR="/home/${TARGET_USER}/Wild_Life_Recordings"
elif id "david" &>/dev/null && [ -d "/home/david" ]; then
  RECORDINGS_DIR="/home/david/Wild_Life_Recordings"
elif [ -d "/home/david" ]; then
  RECORDINGS_DIR="/home/david/Wild_Life_Recordings"
else
  RECORDINGS_DIR="/var/media/Wild_Life_Recordings"
fi

# Remove legacy symlink if it previously pointed to bootfs
if [ -L "${RECORDINGS_DIR}" ]; then
  rm -f "${RECORDINGS_DIR}"
fi

mkdir -p "${RECORDINGS_DIR}"
chmod 775 "${RECORDINGS_DIR}" || true
if id "david" &>/dev/null; then
  chown -R david:david "${RECORDINGS_DIR}" 2>/dev/null || true
elif [ -n "$TARGET_USER" ] && [ "$TARGET_USER" != "root" ]; then
  chown -R "${TARGET_USER}:${TARGET_USER}" "${RECORDINGS_DIR}" 2>/dev/null || true
fi

echo "[3/5] Ensuring MP4 muxer (ffmpeg or MP4Box) is installed for MP4 encapsulation..."
if ! command -v ffmpeg &>/dev/null && ! command -v MP4Box &>/dev/null; then
  apt-get update && (apt-get install -y --no-install-recommends ffmpeg || apt-get install -y --no-install-recommends gpac) || echo "Warning: Could not install ffmpeg/gpac. Raw .h264 fallback will be used."
fi


echo "[4/5] Installing systemd service..."
cp "${SERVICE_SRC}" "${SERVICE_DEST}"
chmod 644 "${SERVICE_DEST}"

echo "[5/5] Enabling service..."
# Remove temporary boot mask from cmdline.txt if present
for CMDLINE in /boot/firmware/cmdline.txt /boot/cmdline.txt; do
  if [ -f "$CMDLINE" ]; then
    sed -i 's/ systemd.mask=squirrel-record.service//' "$CMDLINE"
  fi
done

systemctl daemon-reload
systemctl unmask squirrel-record.service 2>/dev/null || true
systemctl enable squirrel-record.service

echo "=== SquirrelFeeder service installed successfully! ==="
echo "Recordings directory ready at: ${RECORDINGS_DIR}"
echo "(Visible as 'Wild_Life_Recordings' when SD card is read on a Mac)"

