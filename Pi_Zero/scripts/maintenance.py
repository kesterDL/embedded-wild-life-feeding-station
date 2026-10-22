#!/usr/bin/env python3
"""Maintenance Mode & Hardware Profile Manager for Raspberry Pi Media Node.

Manages switching between:
  1. Bench / Developer Mode ('on', 'bench', 'dev'):
     - Auto-shutdown DISABLED (keeps Pi powered on indefinitely).
     - Wi-Fi ENABLED (removes dtoverlay=disable-wifi in config.txt for SSH access).
     - HDMI ENABLED (removes hdmi_blanking=2 in config.txt for monitor debugging).

  2. Autonomous Field Mode ('off', 'field', 'deploy'):
     - Auto-shutdown ENABLED (shuts down OS after 20s recording + signals Arduino ACK).
     - Wi-Fi DISABLED (dtoverlay=disable-wifi in config.txt to save ~30-50 mA).
     - HDMI DISABLED (hdmi_blanking=2 in config.txt to save ~25-30 mA).

Works either:
  - Directly on an attached microSD card on macOS (/Volumes/bootfs or /Volumes/boot)
  - Locally on the Raspberry Pi (/boot/firmware or /boot)
  - Remotely over SSH (--host david@pi-3)
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


def toggle_config_param(config_path: str, param: str, active: bool) -> bool:
    """Enables (uncomments) or disables (comments out) a directive in config.txt.

    Args:
        config_path: Path to config.txt.
        param: Configuration string (e.g. 'dtoverlay=disable-wifi').
        active: If True, line is active (uncommented). If False, commented out.

    Returns:
        True if the file was processed successfully.
    """
    if not os.path.isfile(config_path):
        return False
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        new_lines = []
        found = False
        modified = False

        for line in lines:
            stripped = line.strip()
            # Match exact active line
            if stripped == param:
                found = True
                if active:
                    new_lines.append(line)
                else:
                    new_lines.append(f"# {param}\n")
                    modified = True
            # Match commented version
            elif stripped in [f"# {param}", f"#{param}"]:
                found = True
                if active:
                    new_lines.append(f"{param}\n")
                    modified = True
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)

        # If directive needs to be active and was not present, append it
        if active and not found:
            new_lines.append(f"{param}\n")
            modified = True

        if modified:
            needs_sudo = not os.access(config_path, os.W_OK)
            content = "".join(new_lines)
            if needs_sudo:
                p = subprocess.run(["sudo", "tee", config_path], input=content, text=True, stdout=subprocess.DEVNULL, check=False)
                if p.returncode != 0:
                    return False
            else:
                with open(config_path, "w", encoding="utf-8") as f:
                    f.write(content)
        return True
    except Exception as e:
        print(f"[WARNING] Could not update {config_path}: {e}", file=sys.stderr)
        return False


def set_maintenance_local(
    boot_dir: str,
    enable: bool,
    toggle_hardware: bool = True,
    keep_wifi: bool = False
) -> bool:
    """Enables (Bench Mode) or disables (Field Mode) maintenance on local boot directory.

    Args:
        boot_dir: Directory representing the boot partition (e.g. /Volumes/bootfs or /boot/firmware).
        enable: True for Bench Mode (stay awake, Wi-Fi on), False for Field Mode (auto-shutdown, Wi-Fi off).
        toggle_hardware: If True, toggles Wi-Fi and HDMI directives in config.txt.
        keep_wifi: If True, forces Wi-Fi to remain enabled even in Field Mode.
    """
    success = True
    needs_sudo = not os.access(boot_dir, os.W_OK)

    # 1. Manage flag files
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

    # 2. Manage config.txt Wi-Fi & HDMI directives
    if toggle_hardware:
        config_path = os.path.join(boot_dir, "config.txt")
        if os.path.isfile(config_path):
            if enable:
                # Bench mode: Wi-Fi ON (comment out disable-wifi), HDMI ON (comment out blanking)
                toggle_config_param(config_path, "dtoverlay=disable-wifi", active=False)
                toggle_config_param(config_path, "hdmi_blanking=2", active=False)
            else:
                # Field mode: Wi-Fi OFF (unless keep_wifi is set), HDMI OFF
                disable_wifi = not keep_wifi
                toggle_config_param(config_path, "dtoverlay=disable-wifi", active=disable_wifi)
                toggle_config_param(config_path, "hdmi_blanking=2", active=True)

    # Flush disk buffers so removing the SD card doesn't lose the changes
    try:
        if hasattr(os, "sync"):
            os.sync()
        else:
            subprocess.run(["sync"], check=False)
    except Exception:
        pass

    return success


def set_maintenance_remote(
    host: str,
    enable: bool,
    toggle_hardware: bool = True,
    keep_wifi: bool = False
) -> bool:
    """Enables or disables maintenance mode on a remote Raspberry Pi via SSH."""
    if enable:
        cmd_str = (
            "sudo touch /boot/firmware/maintenance /boot/firmware/no_shutdown 2>/dev/null || "
            "sudo touch /boot/maintenance /boot/no_shutdown; "
        )
        if toggle_hardware:
            cmd_str += (
                "for CFG in /boot/firmware/config.txt /boot/config.txt; do "
                "  if [ -f \"$CFG\" ]; then "
                "    sudo sed -i 's/^[[:space:]]*dtoverlay=disable-wifi/# dtoverlay=disable-wifi/' \"$CFG\"; "
                "    sudo sed -i 's/^[[:space:]]*hdmi_blanking=2/# hdmi_blanking=2/' \"$CFG\"; "
                "  fi; "
                "done; "
            )
    else:
        cmd_str = (
            "sudo rm -f /boot/firmware/maintenance /boot/firmware/no_shutdown "
            "/boot/maintenance /boot/no_shutdown "
            "~/Wild_Life_Recordings/maintenance ~/Wild_Life_Recordings/no_shutdown 2>/dev/null || true; "
        )
        if toggle_hardware:
            cmd_str += (
                "for CFG in /boot/firmware/config.txt /boot/config.txt; do "
                "  if [ -f \"$CFG\" ]; then "
            )
            if not keep_wifi:
                cmd_str += (
                    "    grep -q 'dtoverlay=disable-wifi' \"$CFG\" && "
                    "    sudo sed -i 's/^[[:space:]]*#*[[:space:]]*dtoverlay=disable-wifi/dtoverlay=disable-wifi/' \"$CFG\" || "
                    "    echo 'dtoverlay=disable-wifi' | sudo tee -a \"$CFG\" >/dev/null; "
                )
            cmd_str += (
                "    grep -q 'hdmi_blanking=2' \"$CFG\" && "
                "    sudo sed -i 's/^[[:space:]]*#*[[:space:]]*hdmi_blanking=2/hdmi_blanking=2/' \"$CFG\" || "
                "    echo 'hdmi_blanking=2' | sudo tee -a \"$CFG\" >/dev/null; "
                "  fi; "
                "done; "
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
        description="Switch between Bench/Maintenance Mode and Autonomous Field Mode."
    )
    parser.add_argument(
        "action",
        nargs="?",
        default=None,
        choices=["on", "enable", "bench", "dev", "off", "disable", "field", "deploy", "status"],
        help="Mode to set: 'bench'/'on' (keep awake, Wi-Fi ON), 'field'/'off' (auto-shutdown, Wi-Fi OFF)",
    )
    parser.add_argument(
        "--on",
        dest="flag_on",
        action="store_true",
        help="Enable bench/maintenance mode (Pi stays on, Wi-Fi & HDMI ON)",
    )
    parser.add_argument(
        "--off",
        dest="flag_off",
        action="store_true",
        help="Disable bench mode / apply field optimizations (auto-shutdown ON, Wi-Fi & HDMI OFF)",
    )
    parser.add_argument(
        "--keep-wifi",
        action="store_true",
        help="Keep Wi-Fi enabled even when entering Field Mode (useful for field testing)",
    )
    parser.add_argument(
        "--no-hardware-toggle",
        action="store_true",
        help="Only toggle maintenance flags; do not modify Wi-Fi or HDMI directives in config.txt",
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

    # Determine action from positional or flags
    action = (args.action or "").lower()
    if args.flag_on:
        action = "on"
    elif args.flag_off:
        action = "off"
    elif not action:
        action = "status"

    is_status = action == "status"
    enable = action in ["on", "enable", "bench", "dev"]
    toggle_hardware = not args.no_hardware_toggle

    local_partitions = find_local_boot_partitions()

    # Determine whether to operate on local SD card or remote SSH
    if local_partitions and not args.remote and not args.host:
        target_dir = local_partitions[0]
        if is_status:
            active = get_maintenance_status_local(target_dir)
            cfg_path = os.path.join(target_dir, "config.txt")
            wifi_disabled = False
            hdmi_disabled = False
            if os.path.isfile(cfg_path):
                with open(cfg_path, "r", encoding="utf-8", errors="ignore") as f:
                    cfg_text = f.read()
                    wifi_disabled = "dtoverlay=disable-wifi" in [
                        l.strip() for l in cfg_text.splitlines() if not l.strip().startswith("#")
                    ]
                    hdmi_disabled = "hdmi_blanking=2" in [
                        l.strip() for l in cfg_text.splitlines() if not l.strip().startswith("#")
                    ]

            print(f"Target Boot Partition: {target_dir}")
            print(f"  Mode               : {'BENCH / DEV MODE' if active else 'AUTONOMOUS FIELD MODE'}")
            print(f"  Auto-Shutdown      : {'DISABLED (Pi stays powered on)' if active else 'ENABLED (Pi halts after 20s recording)'}")
            print(f"  Wi-Fi Radio        : {'DISABLED (dtoverlay=disable-wifi)' if wifi_disabled else 'ENABLED'}")
            print(f"  HDMI Circuitry     : {'DISABLED (hdmi_blanking=2)' if hdmi_disabled else 'ENABLED'}")
            return 0

        ok = set_maintenance_local(
            target_dir,
            enable=enable,
            toggle_hardware=toggle_hardware,
            keep_wifi=args.keep_wifi
        )
        if ok:
            if enable:
                print(f"✓ BENCH / MAINTENANCE MODE ENABLED on {target_dir}")
                print("  - Auto-Shutdown : DISABLED (Pi will stay powered on after recording)")
                print("  - Wi-Fi         : ENABLED (dtoverlay=disable-wifi commented out)")
                print("  - HDMI Display  : ENABLED (hdmi_blanking=2 commented out)")
                print("  The Pi is now ready for developer SSH and monitor debugging.")
                print("  When ready for the field, run: ./maintenance.sh field")
            else:
                print(f"✓ AUTONOMOUS FIELD MODE ENABLED on {target_dir}")
                print("  - Auto-Shutdown : ENABLED (Pi will halt after 20s recording)")
                if not args.keep_wifi:
                    print("  - Wi-Fi         : DISABLED (saves ~30-50 mA battery power)")
                else:
                    print("  - Wi-Fi         : KEPT ENABLED (--keep-wifi flag used)")
                print("  - HDMI Display  : DISABLED (saves ~25-30 mA battery power)")
                print("\nNote: To access the Pi again once Wi-Fi is disabled:")
                print("  1. Remove microSD card, insert into Mac, and run: ./maintenance.sh bench")
                print("  2. Or connect a wired Ethernet cable to the Pi 3.")
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
        state_str = "BENCH MODE (Auto-shutdown OFF)" if remote_status else "FIELD MODE (Auto-shutdown ON)"
        print(f"Status on {remote_host}: {state_str}")
        return 0

    if not enable and not args.keep_wifi:
        print("[WARNING] Disabling Wi-Fi over SSH will prevent future SSH connections over Wi-Fi!")
        print("          You will need to use an Ethernet cable or mount the SD card on your Mac to re-enable Wi-Fi.")

    ok = set_maintenance_remote(
        remote_host,
        enable=enable,
        toggle_hardware=toggle_hardware,
        keep_wifi=args.keep_wifi
    )
    if ok:
        if enable:
            print(f"✓ BENCH MODE ENABLED on {remote_host}")
            print("  - Auto-Shutdown : DISABLED (Pi stays powered on)")
            print("  - Wi-Fi & HDMI  : ENABLED for development access")
        else:
            print(f"✓ FIELD MODE ENABLED on {remote_host}")
            print("  - Auto-Shutdown : ENABLED (Pi halts after recording)")
            if not args.keep_wifi:
                print("  - Wi-Fi         : DISABLED on next boot")
            print("  - HDMI          : DISABLED on next boot")
        return 0
    else:
        print(f"[ERROR] Failed to set maintenance mode on '{remote_host}' via SSH.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
