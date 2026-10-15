#!/bin/bash
# ==============================================================================
# SquirrelFeeder MVP: Multi-Hardware Fast-Boot & Power Optimization Script
# ==============================================================================
# Supports:
#   - Raspberry Pi Zero / Zero W (ARMv6 32-bit)
#   - Raspberry Pi 3 (Model B / Model B+ 64-bit Bookworm & Bullseye)
#
# Objective: Automatically detect hardware and apply targeted kernel, systemd,
#            firmware, and power-saving profiles to minimize cold-boot latency.
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<EOF
Usage: sudo $0 [OPTIONS]

Options:
  --auto        Auto-detect hardware model and apply corresponding profile (default)
  --zero        Force Raspberry Pi Zero / Zero W profile (ARMv6 32-bit)
  --pi3, --3b   Force Raspberry Pi 3 / 3B / 3B+ profile (ARMv8 64-bit)
  -h, --help    Display this help message

Examples:
  sudo $0              # Auto-detects connected Pi model
  sudo $0 --pi3        # Explicitly apply Pi 3B optimizations
  sudo $0 --zero       # Explicitly apply Pi Zero optimizations
EOF
  exit 0
}

# Check for help flag before root enforcement
for arg in "$@"; do
  if [ "$arg" == "-h" ] || [ "$arg" == "--help" ]; then
    usage
  fi
done

# ------------------------------------------------------------------------------
# 1. Privilege Check
# ------------------------------------------------------------------------------
if [ "$EUID" -ne 0 ]; then
  echo "Error: Please run as root (sudo $0)"
  exit 1
fi

# ------------------------------------------------------------------------------
# 2. Hardware Detection
# ------------------------------------------------------------------------------
detect_hardware() {
  local model=""
  if [ -f "/proc/device-tree/model" ]; then
    model=$(tr -d '\0' < /proc/device-tree/model 2>/dev/null || cat /proc/device-tree/model 2>/dev/null)
  elif [ -f "/sys/firmware/devicetree/base/model" ]; then
    model=$(tr -d '\0' < /sys/firmware/devicetree/base/model 2>/dev/null || cat /sys/firmware/devicetree/base/model 2>/dev/null)
  elif grep -qi "model" /proc/cpuinfo 2>/dev/null; then
    model=$(grep -i "model" /proc/cpuinfo | head -n 1 | cut -d: -f2 | xargs)
  fi

  local arch
  arch=$(uname -m 2>/dev/null || echo "unknown")

  if [[ "$model" =~ [Zz]ero\ 2 ]]; then
    # Pi Zero 2 W shares the BCM2710 quad-core architecture with Pi 3
    echo "pi3"
  elif [[ "$model" =~ [Zz]ero ]]; then
    echo "zero"
  elif [[ "$model" =~ "Pi 3" || "$model" =~ "3 Model" ]]; then
    echo "pi3"
  elif [[ "$model" =~ "Pi 4" || "$model" =~ "Pi 5" ]]; then
    echo "pi3"
  elif [[ "$arch" == "aarch64" || "$arch" == "arm64" ]]; then
    echo "pi3"
  elif [[ "$arch" =~ armv6 ]]; then
    echo "zero"
  else
    echo "unknown"
  fi
}

# ------------------------------------------------------------------------------
# 3. Parse Command-Line Arguments
# ------------------------------------------------------------------------------
TARGET_PROFILE="auto"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --zero)
      TARGET_PROFILE="zero"
      shift
      ;;
    --pi3|--3b)
      TARGET_PROFILE="pi3"
      shift
      ;;
    --auto)
      TARGET_PROFILE="auto"
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "Unknown option: $1"
      usage
      ;;
  esac
done

RAW_MODEL=""
if [ -f "/proc/device-tree/model" ]; then
  RAW_MODEL=$(tr -d '\0' < /proc/device-tree/model 2>/dev/null || true)
fi

if [ "$TARGET_PROFILE" == "auto" ]; then
  DETECTED=$(detect_hardware)
  if [ "$DETECTED" == "pi3" ]; then
    TARGET_PROFILE="pi3"
  elif [ "$DETECTED" == "zero" ]; then
    TARGET_PROFILE="zero"
  else
    echo "Notice: Could not automatically distinguish between Pi Zero and Pi 3."
    if [ -n "$RAW_MODEL" ]; then
      echo "Hardware model reported: '$RAW_MODEL'"
    fi
    echo "Defaulting to Raspberry Pi 3 profile (safest for quad-core 64-bit kernels)."
    TARGET_PROFILE="pi3"
  fi
fi

echo "======================================================================"
echo "=== SquirrelFeeder OS Optimization Manager                         ==="
echo "======================================================================"
if [ -n "$RAW_MODEL" ]; then
  echo "Detected Hardware : $RAW_MODEL"
fi
echo "Selected Profile  : $TARGET_PROFILE"
echo "======================================================================"

# ------------------------------------------------------------------------------
# 4. Profile Dispatch
# ------------------------------------------------------------------------------

optimize_pi_zero() {
  echo ""
  echo ">>> Applying Raspberry Pi Zero / Zero W Optimization Profile <<<"
  echo ""

  # 1. Mask non-essential services
  echo "[1/4] Masking unnecessary services for Pi Zero..."
  SERVICES=(
    bluetooth.service
    hciuart.service
    # avahi-daemon.service allows mDNS / SSH over USB gadget - keep active for development
    triggerhappy.service
    ModemManager.service
    cups.service
    cups-browsed.service
    apt-daily.service
    apt-daily-upgrade.service
    man-db.service
    keyboard-setup.service
    cloud-init.service
    cloud-init-main.service
    cloud-init-local.service
    cloud-init-network.service
  )

  for s in "${SERVICES[@]}"; do
    if systemctl list-unit-files "$s" &>/dev/null; then
      systemctl disable "$s" 2>/dev/null || true
      systemctl mask "$s" 2>/dev/null || true
    fi
  done

  # Disable cloud-init
  mkdir -p /etc/cloud
  touch /etc/cloud/cloud-init.disabled

  # 2. Add Fast Boot Config to /boot/config.txt or /boot/firmware/config.txt
  echo "[2/4] Optimizing config.txt for Pi Zero..."
  CONFIG_TXT="/boot/config.txt"
  if [ -f "/boot/firmware/config.txt" ]; then
    CONFIG_TXT="/boot/firmware/config.txt"
  fi

  if [ -f "$CONFIG_TXT" ]; then
    # Disable Bluetooth radio (saves ~15-20 mA)
    grep -q "dtoverlay=disable-bt" "$CONFIG_TXT" || echo "dtoverlay=disable-bt" >> "$CONFIG_TXT"

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
  echo "[4/4] Configuring low-power hardware shutoffs in rc.local..."
  RC_LOCAL="/etc/rc.local"
  if [ -f "$RC_LOCAL" ]; then
    if ! grep -q "tvservice -o" "$RC_LOCAL"; then
      sed -i -e '$i /usr/bin/tvservice -o 2>/dev/null || true\n' "$RC_LOCAL"
    fi
  fi

  echo "=== Raspberry Pi Zero optimization complete. Please reboot to take effect. ==="
}

optimize_pi_3b() {
  echo ""
  echo ">>> Applying Raspberry Pi 3 (3B / 3B+) Optimization Profile <<<"
  echo ""

  # Delegate to dedicated optimize_pi3.sh script if present
  if [ -f "${SCRIPT_DIR}/optimize_pi3.sh" ]; then
    bash "${SCRIPT_DIR}/optimize_pi3.sh"
    return
  fi

  # Fallback inline execution if standalone optimize_pi3.sh is missing
  echo "[1/4] Masking Pi 3 & Bookworm background services..."
  SERVICES=(
    bluetooth.service
    hciuart.service
    triggerhappy.service
    ModemManager.service
    cups.service
    cups-browsed.service
    apt-daily.service
    apt-daily.timer
    apt-daily-upgrade.service
    apt-daily-upgrade.timer
    man-db.service
    man-db.timer
    keyboard-setup.service
    cloud-init.service
    cloud-init-main.service
    cloud-init-local.service
    cloud-init-network.service
    systemd-udev-settle.service
    NetworkManager-wait-online.service
    rpi-eeprom-update.service
    raspi-config.service
    systemd-journal-flush.service
  )

  for s in "${SERVICES[@]}"; do
    if systemctl list-unit-files "$s" &>/dev/null; then
      systemctl disable "$s" 2>/dev/null || true
      systemctl mask "$s" 2>/dev/null || true
    fi
  done
  mkdir -p /etc/cloud
  touch /etc/cloud/cloud-init.disabled

  echo "[2/4] Applying Pi 3 firmware & kernel tuning..."
  CONFIG_TXT=""
  CMDLINE_TXT=""
  for candidate in "/Volumes/bootfs" "/Volumes/boot" "/boot/firmware" "/boot"; do
    if [ -d "$candidate" ] && { [ -f "$candidate/config.txt" ] || [ -f "$candidate/cmdline.txt" ]; }; then
      [ -f "$candidate/config.txt" ] && CONFIG_TXT="$candidate/config.txt"
      [ -f "$candidate/cmdline.txt" ] && CMDLINE_TXT="$candidate/cmdline.txt"
      break
    fi
  done

  if [ -n "$CONFIG_TXT" ] && [ -f "$CONFIG_TXT" ]; then
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
    grep -q "arm_boost=1" "$CONFIG_TXT" || echo "arm_boost=1" >> "$CONFIG_TXT"
    grep -q "initial_turbo=30" "$CONFIG_TXT" || echo "initial_turbo=30" >> "$CONFIG_TXT"
    grep -q "boot_delay=0" "$CONFIG_TXT" || echo "boot_delay=0" >> "$CONFIG_TXT"
    grep -q "disable_splash=1" "$CONFIG_TXT" || echo "disable_splash=1" >> "$CONFIG_TXT"
    grep -q "dtoverlay=disable-bt" "$CONFIG_TXT" || echo "dtoverlay=disable-bt" >> "$CONFIG_TXT"
    grep -q "dtparam=audio=off" "$CONFIG_TXT" || echo "dtparam=audio=off" >> "$CONFIG_TXT"
    grep -q "hdmi_blanking=2" "$CONFIG_TXT" || echo "hdmi_blanking=2" >> "$CONFIG_TXT"
  fi

  if [ -n "$CMDLINE_TXT" ] && [ -f "$CMDLINE_TXT" ]; then
    CURRENT_CMDLINE=$(tr -d '\r\n' < "$CMDLINE_TXT")
    FASTBOOT_FLAGS=("quiet" "loglevel=3" "fsck.mode=skip" "fastboot" "systemd.show_status=0")
    MODIFIED=false
    for flag in "${FASTBOOT_FLAGS[@]}"; do
      case " $CURRENT_CMDLINE " in
        *" $flag "*) ;;
        *) CURRENT_CMDLINE="${CURRENT_CMDLINE} ${flag}"; MODIFIED=true ;;
      esac
    done
    [ "$MODIFIED" = true ] && echo "$CURRENT_CMDLINE" > "$CMDLINE_TXT"
  fi

  echo "[3/4] Ensuring /mnt/usb_storage mountpoint exists..."
  mkdir -p /mnt/usb_storage 2>/dev/null || true

  echo "[4/4] Configuring low-power & CPU performance settings..."
  RC_LOCAL="/etc/rc.local"
  if [ -f "$RC_LOCAL" ]; then
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
" "$RC_LOCAL" 2>/dev/null || true
    fi
  fi

  echo "=== Raspberry Pi 3 optimization complete. Please reboot to take effect. ==="
}

case "$TARGET_PROFILE" in
  zero)
    optimize_pi_zero
    ;;
  pi3)
    optimize_pi_3b
    ;;
  *)
    echo "Unknown profile: $TARGET_PROFILE"
    exit 1
    ;;
esac
