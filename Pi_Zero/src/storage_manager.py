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
        use_sd_card: Optional[bool] = None
    ):
        self.directory_name = directory_name
        self.mount_point = mount_point
        # If use_sd_card is not explicitly specified:
        # Default to True when mount_point is None (standard SD card operation).
        # Default to False when mount_point is explicitly specified (external USB mode).
        if use_sd_card is None:
            self.use_sd_card = (mount_point is None)
        else:
            self.use_sd_card = use_sd_card

        self.recordings_dir = self.resolve_recordings_dir()

    def resolve_recordings_dir(self) -> str:
        """Determines the target directory for recordings.

        When targeting the SD card, locates the FAT boot partition visible to macOS:
        1. /boot/firmware/Wild_Life_Recordings (Raspberry Pi OS Bookworm)
        2. /boot/Wild_Life_Recordings (Raspberry Pi OS Bullseye / legacy)
        3. /Volumes/boot/Wild_Life_Recordings (macOS host environment with SD inserted)
        4. Fallback to ./Wild_Life_Recordings (local/testing environment)
        """
        if not self.use_sd_card and self.mount_point:
            return os.path.join(self.mount_point, self.directory_name)

        # Priority search on SD card FAT boot partition mount points
        for candidate_base in ["/boot/firmware", "/boot", "/Volumes/boot", "/Volumes/bootfs"]:
            if os.path.exists(candidate_base) and os.path.isdir(candidate_base):
                return os.path.join(candidate_base, self.directory_name)

        if self.mount_point:
            return os.path.join(self.mount_point, self.directory_name)

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
        if self.use_sd_card:
            os.makedirs(self.recordings_dir, exist_ok=True)
            return True

        # External USB Storage Mode
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

    def generate_video_path(self, timestamp: Optional[str] = None) -> str:
        """Generates a standardized MP4 video file path within the recordings directory."""
        if not timestamp:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        os.makedirs(self.recordings_dir, exist_ok=True)
        return os.path.join(self.recordings_dir, f"clip_{timestamp}.mp4")

