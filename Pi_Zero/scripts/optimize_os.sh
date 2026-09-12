#!/bin/bash
# ==============================================================================
# SquirrelFeeder MVP: Raspberry Pi OS Lite Fast-Boot & Power Optimization Script
# ==============================================================================
# Target: Raspberry Pi Zero W running Raspberry Pi OS Lite (32-bit Bullseye/Bookworm)
# Objective: Reduce cold-boot time to < 15 seconds and conserve battery power.
# ==============================================================================

set -e

if [ "$EUID" -ne 0 ]; then
  echo "Error: Please run as root (sudo ./optimize_os.sh)"
  exit 1
fi

echo "=== Configuring Fast Boot and Power Optimizations ==="

# 1. Disable Non-Essential Services
echo "[1/4] Masking unnecessary services..."
SERVICES=(
  bluetooth.service
  hciuart.service
  # avahi-daemon.service this service allows for ssh over usb. Keep active for now.
  triggerhappy.service
  ModemManager.service
  cups.service
  cups-browsed.service
  apt-daily.service
  apt-daily-upgrade.service
  man-db.service
)

for s in "${SERVICES[@]}"; do
  if systemctl list-unit-files "$s" &>/dev/null; then
    systemctl disable "$s" 2>/dev/null || true
    systemctl mask "$s" 2>/dev/null || true
  fi
done

# 2. Add Fast Boot Config to /boot/config.txt
echo "[2/4] Optimizing /boot/config.txt..."
CONFIG_TXT="/boot/config.txt"
if [ -f "/boot/firmware/config.txt" ]; then
  CONFIG_TXT="/boot/firmware/config.txt"
fi

if [ -f "$CONFIG_TXT" ]; then
  # Disable Bluetooth & Wi-Fi radios
  grep -q "dtoverlay=disable-bt" "$CONFIG_TXT" || echo "dtoverlay=disable-bt" >> "$CONFIG_TXT"
  grep -q "dtoverlay=disable-wifi" "$CONFIG_TXT" || echo "dtoverlay=disable-wifi" >> "$CONFIG_TXT"

  # Fast boot flags
  grep -q "boot_delay=0" "$CONFIG_TXT" || echo "boot_delay=0" >> "$CONFIG_TXT"
  grep -q "disable_splash=1" "$CONFIG_TXT" || echo "disable_splash=1" >> "$CONFIG_TXT"
  grep -q "initial_turbo=30" "$CONFIG_TXT" || echo "initial_turbo=30" >> "$CONFIG_TXT"

  # Disable HDMI to save ~25-30 mA
  grep -q "hdmi_blanking=2" "$CONFIG_TXT" || echo "hdmi_blanking=2" >> "$CONFIG_TXT"
fi

# 3. Create Mountpoint for Removable USB Drive
echo "[3/4] Ensuring /mnt/usb_storage mountpoint exists..."
mkdir -p /mnt/usb_storage

# 4. Turn Off HDMI and LEDs in rc.local
echo "[4/4] Configuring low-power hardware shutoffs..."
RC_LOCAL="/etc/rc.local"
if [ -f "$RC_LOCAL" ]; then
  if ! grep -q "tvservice -o" "$RC_LOCAL"; then
    sed -i -e '$i /usr/bin/tvservice -o 2>/dev/null || true\n' "$RC_LOCAL"
  fi
fi

echo "=== Optimization configuration complete. Please reboot to take effect. ==="
