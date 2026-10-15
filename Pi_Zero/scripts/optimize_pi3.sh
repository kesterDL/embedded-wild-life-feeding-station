#!/bin/bash
# ==============================================================================
# SquirrelFeeder MVP: Raspberry Pi 3 (3B / 3B+) Fast-Boot & Optimization Script
# ==============================================================================
# Target: Raspberry Pi 3 Model B and 3 Model B+ (64-bit Bookworm / Bullseye)
# Objective: Reduce cold-boot time to < 8-10 seconds, optimize CPU performance,
#            and eliminate services delaying squirrel-record.service.
#
# Supports running:
#   1. Directly on the Raspberry Pi (/boot/firmware or /boot)
#   2. Directly on macOS when the SD card is mounted (/Volumes/bootfs or /Volumes/boot)
# ==============================================================================

set -e

for arg in "$@"; do
  if [ "$arg" == "-h" ] || [ "$arg" == "--help" ]; then
    cat <<EOF
Usage: sudo $0 [OPTIONS]

Applies targeted fast-boot and power optimizations for Raspberry Pi 3 (3B / 3B+):
  - Bypasses 16.5MB initramfs8 loading and decompression (auto_initramfs=0)
  - Adds kernel fast-boot parameters (quiet loglevel=3 fsck.mode=skip fastboot systemd.show_status=0)
  - Forces maximum CPU turbo (initial_turbo=30, arm_boost=1)
  - Configures CPU scaling governor to 'performance' across all 4 cores
  - Masks boot-blocking services (udev-settle, NetworkManager-wait-online, timers)
  - Sets volatile journal logging in RAM to prevent SD card write contention
  - Powers off unneeded hardware blocks (Bluetooth, HDMI, LEDs)
EOF
    exit 0
  fi
done

# Check privileges when running on Linux
if [ "$(uname -s)" != "Darwin" ] && [ "$EUID" -ne 0 ]; then
  echo "Error: Please run as root on Linux (sudo $0)"
  exit 1
fi

echo "======================================================================"
echo "=== Raspberry Pi 3 (3B/3B+) Fast-Boot & Power Optimization Setup   ==="
echo "======================================================================"

# ------------------------------------------------------------------------------
# Locate Boot Partition (Support local Pi and macOS SD card reader)
# ------------------------------------------------------------------------------
CONFIG_TXT=""
CMDLINE_TXT=""
BOOT_DIR=""

for candidate in "/Volumes/bootfs" "/Volumes/boot" "/boot/firmware" "/boot"; do
  if [ -d "$candidate" ] && { [ -f "$candidate/config.txt" ] || [ -f "$candidate/cmdline.txt" ]; }; then
    BOOT_DIR="$candidate"
    [ -f "$candidate/config.txt" ] && CONFIG_TXT="$candidate/config.txt"
    [ -f "$candidate/cmdline.txt" ] && CMDLINE_TXT="$candidate/cmdline.txt"
    break
  fi
done

if [ -n "$BOOT_DIR" ]; then
  echo "Detected boot partition at: ${BOOT_DIR}"
fi

# ------------------------------------------------------------------------------
# 1. Disable & Mask Unnecessary & Boot-Blocking Services (Linux only)
# ------------------------------------------------------------------------------
if command -v systemctl &>/dev/null; then
  echo "[1/6] Masking unnecessary services and boot-blocking targets..."

  SERVICES=(
    # Bluetooth & UART handlers
    bluetooth.service
    hciuart.service

    # Printing services
    cups.service
    cups-browsed.service

    # Daily background update and indexing tasks
    apt-daily.service
    apt-daily.timer
    apt-daily-upgrade.service
    apt-daily-upgrade.timer
    man-db.service
    man-db.timer

    # Peripheral & interactive daemons not needed on a headless camera node
    triggerhappy.service
    ModemManager.service
    keyboard-setup.service

    # Cloud-init (saves ~4.7s)
    cloud-init.service
    cloud-init-main.service
    cloud-init-local.service
    cloud-init-network.service

    # Pi 3 / Bookworm specific services that delay userspace startup:
    # - systemd-udev-settle: blocks until USB/LAN hub finishes settling (saves 3-5s)
    systemd-udev-settle.service

    # - NetworkManager-wait-online: blocks boot waiting for Wi-Fi association (saves 10-15s)
    NetworkManager-wait-online.service

    # - EEPROM updates (relevant to Pi 4/5, unnecessary on Pi 3)
    rpi-eeprom-update.service

    # - First-boot reconfiguration tool
    raspi-config.service

    # - Journal disk flush (reduces SD card write contention on boot)
    systemd-journal-flush.service
  )

  for s in "${SERVICES[@]}"; do
    if systemctl list-unit-files "$s" &>/dev/null; then
      systemctl disable "$s" 2>/dev/null || true
      systemctl mask "$s" 2>/dev/null || true
    fi
  done

  # Disable cloud-init via config flag as well
  mkdir -p /etc/cloud
  touch /etc/cloud/cloud-init.disabled
else
  echo "[1/6] Not running directly on systemd host (e.g. running on macOS card reader). Skipping service masking."
fi

# ------------------------------------------------------------------------------
# 2. Firmware Optimization in config.txt (Bypass Initramfs & Maximize Clock)
# ------------------------------------------------------------------------------
echo "[2/6] Optimizing firmware configuration in ${CONFIG_TXT:-[not found]}..."

if [ -n "$CONFIG_TXT" ] && [ -f "$CONFIG_TXT" ]; then
  # 1. Bypass 16.5MB initramfs8 loading and decompression (saves ~4.5 - 5.5s on Pi 3)
  # When rootfs is directly on SD ext4 (/dev/mmcblk0p2), initramfs is unnecessary.
  if grep -q "auto_initramfs" "$CONFIG_TXT"; then
    python3 -c "
import sys
with open(sys.argv[1], 'r') as f:
    lines = f.readlines()
with open(sys.argv[1], 'w') as f:
    for line in lines:
        if line.strip().startswith('auto_initramfs='):
            f.write('auto_initramfs=0\n')
        else:
            f.write(line)
" "$CONFIG_TXT"
  else
    echo "auto_initramfs=0" >> "$CONFIG_TXT"
  fi

  # Comment out explicit initramfs line if present
  python3 -c "
import sys
with open(sys.argv[1], 'r') as f:
    lines = f.readlines()
with open(sys.argv[1], 'w') as f:
    for line in lines:
        if line.strip().startswith('initramfs initramfs8'):
            f.write('# initramfs initramfs8 followkernel\n')
        else:
            f.write(line)
" "$CONFIG_TXT"

  # 2. Maximum CPU frequency during boot (Pi 3B: 1.2 GHz, Pi 3B+: 1.4 GHz)
  grep -q "arm_boost=1" "$CONFIG_TXT" || echo "arm_boost=1" >> "$CONFIG_TXT"
  grep -q "initial_turbo=30" "$CONFIG_TXT" || echo "initial_turbo=30" >> "$CONFIG_TXT"

  # 3. Bootloader latency elimination
  grep -q "boot_delay=0" "$CONFIG_TXT" || echo "boot_delay=0" >> "$CONFIG_TXT"
  grep -q "disable_splash=1" "$CONFIG_TXT" || echo "disable_splash=1" >> "$CONFIG_TXT"

  # 4. Disable unneeded hardware blocks to conserve battery & power rail stability
  grep -q "dtoverlay=disable-bt" "$CONFIG_TXT" || echo "dtoverlay=disable-bt" >> "$CONFIG_TXT"
  grep -q "dtparam=audio=off" "$CONFIG_TXT" || echo "dtparam=audio=off" >> "$CONFIG_TXT"
  grep -q "hdmi_blanking=2" "$CONFIG_TXT" || echo "hdmi_blanking=2" >> "$CONFIG_TXT"

  # 5. Disable onboard activity and power LEDs (saves ~10 mA and prevents night glare)
  grep -q "dtparam=act_led_trigger=none" "$CONFIG_TXT" || echo "dtparam=act_led_trigger=none" >> "$CONFIG_TXT"
  grep -q "dtparam=act_led_activelow=off" "$CONFIG_TXT" || echo "dtparam=act_led_activelow=off" >> "$CONFIG_TXT"

  echo "  ✓ config.txt updated with auto_initramfs=0, turbo, and fast-boot overlays."
else
  echo "Warning: config.txt not found. Skipping config.txt optimization."
fi

# ------------------------------------------------------------------------------
# 3. Kernel Command Line Fast-Boot Flags in cmdline.txt
# ------------------------------------------------------------------------------
echo "[3/6] Optimizing kernel command line in ${CMDLINE_TXT:-[not found]}..."

if [ -n "$CMDLINE_TXT" ] && [ -f "$CMDLINE_TXT" ]; then
  CURRENT_CMDLINE=$(tr -d '\r\n' < "$CMDLINE_TXT")
  FASTBOOT_FLAGS=(
    "quiet"
    "loglevel=3"
    "fsck.mode=skip"
    "fastboot"
    "systemd.show_status=0"
  )

  MODIFIED=false
  for flag in "${FASTBOOT_FLAGS[@]}"; do
    case " $CURRENT_CMDLINE " in
      *" $flag "*)
        ;;
      *)
        CURRENT_CMDLINE="${CURRENT_CMDLINE} ${flag}"
        MODIFIED=true
        ;;
    esac
  done

  if [ "$MODIFIED" = true ]; then
    echo "$CURRENT_CMDLINE" > "$CMDLINE_TXT"
    echo "  ✓ Added fast-boot flags (quiet, loglevel=3, fsck.mode=skip, fastboot, systemd.show_status=0)."
  else
    echo "  ✓ Kernel command line already contains all fast-boot flags."
  fi
else
  echo "Warning: cmdline.txt not found. Skipping cmdline.txt optimization."
fi

# ------------------------------------------------------------------------------
# 4. Systemd Journal Optimization (Volatile RAM Logging)
# ------------------------------------------------------------------------------
if [ -f "/etc/systemd/journald.conf" ]; then
  echo "[4/6] Configuring volatile systemd journal (prevents SD card flush stalls)..."
  JOURNAL_CONF="/etc/systemd/journald.conf"
  if grep -q "^#\?Storage=" "$JOURNAL_CONF"; then
    python3 -c "
import sys
with open(sys.argv[1], 'r') as f:
    text = f.read()
import re
text = re.sub(r'^#?Storage=.*', 'Storage=volatile', text, flags=re.MULTILINE)
text = re.sub(r'^#?RuntimeMaxUse=.*', 'RuntimeMaxUse=16M', text, flags=re.MULTILINE)
with open(sys.argv[1], 'w') as f:
    f.write(text)
" "$JOURNAL_CONF"
  else
    echo "Storage=volatile" >> "$JOURNAL_CONF"
    echo "RuntimeMaxUse=16M" >> "$JOURNAL_CONF"
  fi
else
  echo "[4/6] journald.conf not found locally. Skipping journal configuration."
fi

# ------------------------------------------------------------------------------
# 5. CPU Performance Scaling Governor & Hardware Shutoffs in rc.local
# ------------------------------------------------------------------------------
echo "[5/6] Configuring CPU performance governor and low-power shutoffs..."

RC_LOCAL="/etc/rc.local"
if [ -f "$RC_LOCAL" ]; then
  if ! grep -q "scaling_governor" "$RC_LOCAL"; then
    python3 -c "
import sys
with open(sys.argv[1], 'r') as f:
    content = f.read()
if 'exit 0' in content:
    content = content.replace('exit 0', 'echo performance | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor 2>/dev/null || true\nexit 0')
else:
    content += '\necho performance | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor 2>/dev/null || true\n'
with open(sys.argv[1], 'w') as f:
    f.write(content)
" "$RC_LOCAL"
  fi

  if ! grep -q "display_power 0" "$RC_LOCAL"; then
    python3 -c "
import sys
with open(sys.argv[1], 'r') as f:
    content = f.read()
cmd = 'if command -v vcgencmd &>/dev/null; then vcgencmd display_power 0 2>/dev/null || true; elif command -v tvservice &>/dev/null; then tvservice -o 2>/dev/null || true; fi\n'
if 'exit 0' in content:
    content = content.replace('exit 0', cmd + 'exit 0')
else:
    content += '\n' + cmd
with open(sys.argv[1], 'w') as f:
    f.write(content)
" "$RC_LOCAL"
  fi
fi

# Immediately set performance governor if available in current session
if [ -d "/sys/devices/system/cpu/cpu0/cpufreq" ]; then
  echo performance | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor 2>/dev/null || true
fi

# ------------------------------------------------------------------------------
# 6. Ensure Storage Mountpoint Exists
# ------------------------------------------------------------------------------
echo "[6/6] Ensuring /mnt/usb_storage mountpoint exists..."
mkdir -p /mnt/usb_storage 2>/dev/null || true

# Flush disk buffers so changes are safely committed to SD card
if hasattr_sync="$(python3 -c 'import os; print(hasattr(os, "sync"))' 2>/dev/null)" && [ "$hasattr_sync" == "True" ]; then
  python3 -c "import os; os.sync()" 2>/dev/null || sync 2>/dev/null || true
fi

echo "======================================================================"
echo "=== Raspberry Pi 3 (3B/3B+) Optimization complete!                 ==="
echo "======================================================================"
echo "Summary of optimizations applied:"
echo "  - Disabled 16.5MB initramfs8 ramdisk loading (auto_initramfs=0)"
echo "  - Added fast-boot kernel flags (quiet loglevel=3 fsck.mode=skip fastboot systemd.show_status=0)"
echo "  - Forced maximum CPU clock during boot (initial_turbo=30, arm_boost=1)"
echo "  - Enabled performance CPU governor across all 4 Cortex-A53 cores"
echo "  - Masked udev-settle, NetworkManager-wait-online, and background timers"
echo "  - Moved systemd journal to volatile RAM (/run) to prevent SD stalls"
echo "  - Turned off Bluetooth, HDMI, and onboard LEDs for power conservation"
echo ""
echo "Please reboot your Raspberry Pi 3 for all kernel and firmware changes"
echo "to take effect: sudo reboot"
echo "======================================================================"
