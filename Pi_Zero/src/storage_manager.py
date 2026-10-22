"""Storage Manager for Raspberry Pi Zero W Media Node.

Handles storage discovery, directory management, and filesystem synchronization
for video recordings. By default, saves recordings to a dedicated 'Wild_Life_Recordings'
directory on the SD card's FAT boot partition so they are directly accessible
when the SD card is plugged into a Mac.
"""

import datetime
import glob
import logging
import os
import re
import subprocess
from typing import Optional

logger = logging.getLogger("StorageManager")


class StorageNotFoundError(Exception):
    """Raised when no suitable storage block device or path is available."""
    pass


class StorageManager:
    DEFAULT_DIR_NAME = "Wild_Life_Recordings"

    def __init__(
        self,
        mount_point: Optional[str] = None,
        directory_name: str = DEFAULT_DIR_NAME,
        use_sd_card: Optional[bool] = None,
        sequence_file: Optional[str] = None,
    ):
        self.directory_name = directory_name
        self.mount_point = mount_point
        # If use_sd_card is True: explicitly targets the FAT boot partition.
        # If mount_point is specified: external USB storage mode.
        # Default (mount_point is None and use_sd_card is None/False):
        # targets the 120+ GB ext4 root partition (/home/david/Wild_Life_Recordings).
        self.use_sd_card = bool(use_sd_card)

        self.recordings_dir = self.resolve_recordings_dir()
        self.sequence_file = sequence_file or self.resolve_sequence_file_path()

    def resolve_sequence_file_path(self) -> str:
        """Determines the persistent path for the monotonic sequence counter."""
        candidates = [
            "/home/david/.squirrel_sequence",
            "/var/lib/squirrelfeeder/sequence",
        ]
        for c in candidates:
            parent = os.path.dirname(c)
            if os.path.exists(parent) and os.path.isdir(parent) and os.access(parent, os.W_OK):
                return c

        return os.path.expanduser("~/.squirrel_sequence")

    def resolve_recordings_dir(self) -> str:
        """Determines the target directory for recordings.

        1. External USB storage: when mount_point is explicitly specified.
        2. Explicit SD card FAT boot partition: only when use_sd_card is True.
        3. Ext4 root partition (default): utilizes the full 120+ GB root filesystem
           at /home/david/Wild_Life_Recordings or /var/media/Wild_Life_Recordings.
        4. Fallback to ./Wild_Life_Recordings for local host / testing.
        """
        if self.mount_point:
            return os.path.join(self.mount_point, self.directory_name)

        # Explicit request for SD card FAT boot partition
        if self.use_sd_card:
            for candidate_base in ["/boot/firmware", "/boot", "/Volumes/boot", "/Volumes/bootfs"]:
                if os.path.exists(candidate_base) and os.path.isdir(candidate_base):
                    return os.path.join(candidate_base, self.directory_name)

        # Standard ext4 rootfs partition location (120+ GB storage)
        for ext4_candidate in ["/home/david", "/var/media"]:
            if os.path.exists(ext4_candidate) and os.path.isdir(ext4_candidate):
                target = os.path.join(ext4_candidate, self.directory_name)
                # If target is a legacy symlink pointing to the small bootfs, remove it
                if os.path.islink(target):
                    try:
                        dest = os.readlink(target)
                        if "boot" in dest:
                            os.unlink(target)
                    except OSError:
                        pass
                return target

        # Fallback for development / desktop runs
        return os.path.abspath(self.directory_name)

    def find_usb_device(self) -> Optional[str]:
        """Scans /dev/ for removable USB block devices.

        Prioritizes partitioned storage (e.g. /dev/sda1) before falling
        back to raw devices (e.g. /dev/sda).
        """
        partitions = sorted(glob.glob("/dev/sd[a-z][0-9]*"))
        if partitions:
            return partitions[0]

        disks = sorted(glob.glob("/dev/sd[a-z]"))
        if disks:
            return disks[0]

        return None

    def mount(self) -> bool:
        """Ensures the storage directory is ready and writable.

        For SD card storage: verifies and creates the directory on the boot filesystem.
        For USB storage: discovers and mounts the external USB drive.

        Raises:
            StorageNotFoundError: If external storage device is required but not present.
        """
        if self.use_sd_card or not self.mount_point:
            os.makedirs(self.recordings_dir, exist_ok=True)
            return True

        # External USB Storage Mode (when mount_point is specified)
        device = self.find_usb_device()
        if not device:
            raise StorageNotFoundError(
                "No USB storage device detected in /dev/sd*"
            )

        if self.mount_point:
            os.makedirs(self.mount_point, exist_ok=True)
            if not os.path.ismount(self.mount_point):
                result = subprocess.run(
                    ["mount", "-t", "auto", "-o", "rw", device, self.mount_point],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                if result.returncode != 0:
                    raise RuntimeError(f"Failed to mount {device}: {result.stderr}")

        os.makedirs(self.recordings_dir, exist_ok=True)
        return True

    def unmount(self) -> bool:
        """Flushes disk buffers and unmounts removable storage cleanly."""
        # 1. Flush kernel disk buffers to hardware (critical for SD card lifespan & FAT integrity)
        os.sync()
        try:
            subprocess.run(["sync"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        except OSError:
            pass

        # 2. Unmount external USB storage if mounted
        if self.mount_point and os.path.ismount(self.mount_point):
            result = subprocess.run(
                ["umount", self.mount_point],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            if result.returncode != 0:
                # Retry with lazy unmount if busy
                result_lazy = subprocess.run(
                    ["umount", "-l", self.mount_point],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                return result_lazy.returncode == 0

        return True

    def _get_next_sequence(self) -> int:
        """Reads and increments the monotonic sequence counter.

        Falls back to scanning existing files in recordings_dir if sequence_file does not exist.
        """
        current_seq = 0
        if self.sequence_file and os.path.exists(self.sequence_file):
            try:
                with open(self.sequence_file, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content.isdigit():
                        current_seq = int(content)
            except OSError as e:
                logger.warning(f"Failed to read sequence file {self.sequence_file}: {e}")

        # Fallback to scanning existing clips if sequence file is missing or was 0
        if current_seq == 0 and os.path.isdir(self.recordings_dir):
            try:
                found_numbers = []
                for entry in os.scandir(self.recordings_dir):
                    if entry.is_file():
                        match = re.search(r"clip_(\d+)", entry.name)
                        if match:
                            found_numbers.append(int(match.group(1)))
                if found_numbers:
                    current_seq = max(found_numbers)
            except OSError:
                pass

        next_seq = current_seq + 1

        if self.sequence_file:
            try:
                os.makedirs(os.path.dirname(os.path.abspath(self.sequence_file)), exist_ok=True)
                with open(self.sequence_file, "w", encoding="utf-8") as f:
                    f.write(str(next_seq))
            except OSError as e:
                logger.warning(f"Failed to write sequence file {self.sequence_file}: {e}")

        return next_seq

    @staticmethod
    def parse_throttled_flag(throttled_state: Optional[str]) -> str:
        """Parses vcgencmd throttled state into pwrOK or pwrWARN.

        Format from vcgencmd get_throttled is typically 'throttled=0x50005' or '0x0'.
        Non-zero hex values indicate active or past undervoltage/throttling.
        """
        if not throttled_state:
            return "pwrOK"
        match = re.search(r"0x([0-9a-fA-F]+)", str(throttled_state))
        if match:
            try:
                val = int(match.group(1), 16)
                return "pwrWARN" if val > 0 else "pwrOK"
            except ValueError:
                pass
        return "pwrOK"

    def generate_video_path(
        self,
        uptime_s: Optional[float] = None,
        throttled_state: Optional[str] = None,
        seq: Optional[int] = None,
    ) -> str:
        """Generates a standardized MP4 video file path with monotonic sequence and cycle diagnostics.

        Format:
            clip_{SEQ:05d}_boot{UPTIME}s_{PWR}.mp4
        Example:
            clip_00042_boot16s_pwrOK.mp4
        """
        if seq is None:
            seq = self._get_next_sequence()

        uptime_int = int(round(uptime_s)) if uptime_s is not None else 0
        pwr_flag = self.parse_throttled_flag(throttled_state)

        filename = f"clip_{seq:05d}_boot{uptime_int}s_{pwr_flag}.mp4"
        os.makedirs(self.recordings_dir, exist_ok=True)
        return os.path.join(self.recordings_dir, filename)

