#!/bin/bash
# ==============================================================================
# Raspberry Pi Media Node: Maintenance Mode Toggle
# ==============================================================================
# Usage:
#   ./maintenance.sh          # Enables maintenance mode (prevents auto-shutdown)
#   ./maintenance.sh on       # Enables maintenance mode
#   ./maintenance.sh off      # Disables maintenance mode (field deployment mode)
#   ./maintenance.sh status   # Shows current maintenance mode status
# ==============================================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${SCRIPT_DIR}/maintenance.py" "$@"
