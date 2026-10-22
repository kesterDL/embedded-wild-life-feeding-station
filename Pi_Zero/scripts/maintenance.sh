#!/bin/bash
# ==============================================================================
# Raspberry Pi Media Node: Maintenance / Field Profile Switcher
# ==============================================================================
# Modes:
#   Bench / Developer Mode ('bench' or 'on'):
#     - Auto-shutdown DISABLED (keeps Pi online for development)
#     - Wi-Fi ENABLED (allows SSH connections)
#     - HDMI ENABLED (allows monitor output)
#
#   Field Deployment Mode ('field' or 'off'):
#     - Auto-shutdown ENABLED (halts after 20s recording + Arduino ACK)
#     - Wi-Fi DISABLED (dtoverlay=disable-wifi to save battery power)
#     - HDMI DISABLED (hdmi_blanking=2 to save battery power)
#
# Usage:
#   ./maintenance.sh bench           # Prepare Pi for workbench testing & SSH
#   ./maintenance.sh field           # Prepare Pi for field deployment
#   ./maintenance.sh field --keep-wifi # Field mode with Wi-Fi enabled for testing
#   ./maintenance.sh status          # View current profile & hardware status
# ==============================================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${SCRIPT_DIR}/maintenance.py" "$@"
