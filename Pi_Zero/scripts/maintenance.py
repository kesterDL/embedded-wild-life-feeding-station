#!/usr/bin/env python3
"""Maintenance Mode Manager for Raspberry Pi Media Node.

Enables, disables, or checks maintenance mode on an attached microSD card or
remote Raspberry Pi. Maintenance mode prevents automatic system shutdown (poweroff)
after recording clips, keeping the device online for development, debugging, and file transfers.
"""

import argparse
import glob
import os
import subprocess
import sys
from typing import List, Optional

FLAG_NAMES = ["maintenance", "no_shutdown"]
DEFAULT_REMOTE_HOSTS = ["david@pi-3", "david@pi-zero.local"]


def find_local_boot_partitions() -> List[str]:
    """Finds boot partition paths on the local machine (macOS mount or Linux boot)."""
    candidates = [
        # macOS SD card mounts
        "/Volumes/bootfs",
        "/Volumes/boot",
        # Linux / Raspberry Pi OS local paths
        "/boot/firmware",
        "/boot",
    ]
    found = []
    for c in candidates:
        if os.path.isdir(c):
            found.append(c)

    # Dynamic search for any other mounted volume on macOS containing Pi boot files
    if os.path.isdir("/Volumes"):
        for vol in glob.glob("/Volumes/*"):
            if vol not in found and os.path.isdir(vol):
                if os.path.exists(os.path.join(vol, "config.txt")) or os.path.exists(
                    os.path.join(vol, "cmdline.txt")
                ):
                    found.append(vol)

    return found


def get_maintenance_status_local(boot_dir: str) -> bool:
    """Returns True if any maintenance flag file exists in the given boot directory."""
    return any(os.path.exists(os.path.join(boot_dir, name)) for name in FLAG_NAMES)


def set_maintenance_local(boot_dir: str, enable: bool) -> bool:
    """Enables or disables maintenance mode on the given local boot directory."""
    success = True
    needs_sudo = not os.access(boot_dir, os.W_OK)
    for name in FLAG_NAMES:
        target = os.path.join(boot_dir, name)
        try:
            if enable:
                if needs_sudo:
                    res = subprocess.run(["sudo", "touch", target], check=False)
                    if res.returncode != 0:
                        success = False
                else:
                    with open(target, "w") as f:
                        f.write("# Maintenance mode flag: prevents auto-shutdown\n")
            else:
                if os.path.exists(target):
                    if needs_sudo:
                        res = subprocess.run(["sudo", "rm", "-f", target], check=False)
                        if res.returncode != 0:
                            success = False
                    else:
                        os.remove(target)
        except OSError as e:
            print(f"[ERROR] Failed to update {target}: {e}", file=sys.stderr)
            success = False

    # Also clean ~/Wild_Life_Recordings if flags were created there
    if not enable:
        for home_dir in [
            os.path.expanduser("~/Wild_Life_Recordings"),
            os.path.expanduser("~/SquirrelFeeder/Wild_Life_Recordings")
        ]:
            for name in FLAG_NAMES:
                flag = os.path.join(home_dir, name)
                if os.path.exists(flag):
                    try:
                        os.remove(flag)
                    except OSError:
                        pass

    # Flush disk buffers so removing the SD card doesn't lose the flag
    try:
        if hasattr(os, "sync"):
            os.sync()
        else:
            subprocess.run(["sync"], check=False)
    except Exception:
        pass

    return success


def set_maintenance_remote(host: str, enable: bool) -> bool:
    """Enables or disables maintenance mode on a remote Raspberry Pi via SSH."""
    if enable:
        cmd_str = (
            "sudo touch /boot/firmware/maintenance /boot/firmware/no_shutdown 2>/dev/null || "
            "sudo touch /boot/maintenance /boot/no_shutdown"
        )
    else:
        cmd_str = (
            "sudo rm -f /boot/firmware/maintenance /boot/firmware/no_shutdown "
            "/boot/maintenance /boot/no_shutdown "
            "~/Wild_Life_Recordings/maintenance ~/Wild_Life_Recordings/no_shutdown 2>/dev/null || true"
        )

    res = subprocess.run(["ssh", "-tt", "-o", "ConnectTimeout=5", host, cmd_str], check=False)
    return res.returncode == 0


def check_maintenance_remote(host: str) -> Optional[bool]:
    """Checks maintenance mode status on remote Raspberry Pi via SSH."""
    check_cmd = (
        "test -f /boot/firmware/maintenance || test -f /boot/firmware/no_shutdown || "
        "test -f /boot/maintenance || test -f /boot/no_shutdown || "
        "test -f ~/Wild_Life_Recordings/maintenance"
    )
    res = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=5", host, check_cmd],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if res.returncode == 0:
        return True
    elif res.returncode == 1:
        return False
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enable, disable, or check Raspberry Pi maintenance mode."
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="on",
        choices=["on", "enable", "off", "disable", "status"],
        help="Action to perform (default: 'on')",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Optional SSH host (e.g. david@pi-3). If specified, manages maintenance over SSH.",
    )
    parser.add_argument(
        "--remote",
        action="store_true",
        help="Force remote SSH execution instead of local SD card check.",
    )

    args = parser.parse_args()
    action = args.action.lower()
    enable = action in ["on", "enable"]
    is_status = action == "status"

    local_partitions = find_local_boot_partitions()

    # Determine whether to operate on local SD card or remote SSH
    if local_partitions and not args.remote and not args.host:
        target_dir = local_partitions[0]
        if is_status:
            active = get_maintenance_status_local(target_dir)
            state_str = "ENABLED (Auto-shutdown is OFF)" if active else "DISABLED (Auto-shutdown is ON - Field mode)"
            print(f"Target: Local SD Card ({target_dir})")
            print(f"Status: {state_str}")
            return 0

        ok = set_maintenance_local(target_dir, enable)
        if ok:
            if enable:
                print(f"✓ Maintenance mode ENABLED on SD Card: {target_dir}")
                print("  Flags created: 'maintenance', 'no_shutdown'")
                print("  The Raspberry Pi will stay powered on after recording.")
                print("  (Tip: Run './maintenance.sh off' before deploying to the field)")
            else:
                print(f"✓ Maintenance mode DISABLED on SD Card: {target_dir}")
                print("  The Raspberry Pi will automatically power off after recording (autonomous field mode).")
            return 0
        return 1

    # Remote SSH path
    remote_host = args.host or DEFAULT_REMOTE_HOSTS[0]
    print(f"Connecting to remote host: {remote_host}...")

    if is_status:
        remote_status = check_maintenance_remote(remote_host)
        if remote_status is None:
            print(f"[ERROR] Could not reach remote host '{remote_host}' via SSH.", file=sys.stderr)
            return 1
        state_str = "ENABLED (Auto-shutdown is OFF)" if remote_status else "DISABLED (Auto-shutdown is ON - Field mode)"
        print(f"Status on {remote_host}: {state_str}")
        return 0

    ok = set_maintenance_remote(remote_host, enable)
    if ok:
        if enable:
            print(f"✓ Maintenance mode ENABLED on {remote_host}")
            print("  The Raspberry Pi will stay powered on after recording.")
        else:
            print(f"✓ Maintenance mode DISABLED on {remote_host}")
            print("  The Raspberry Pi will automatically power off after recording (field mode).")
        return 0
    else:
        print(f"[ERROR] Failed to set maintenance mode on '{remote_host}' via SSH.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
