"""Storage Manager for Raspberry Pi Zero W Media Node.

Handles removable USB storage discovery, filesystem mounting,
atomic sync, and unmounting to prevent corruption across power cycles.
"""

import datetime
import glob
import os
import subprocess
from typing import Optional


class StorageNotFoundError(Exception):
    """Raised when no suitable USB block device is present."""
    pass


class StorageManager:
    def __init__(self, mount_point: str = "/mnt/usb_storage"):
        self.mount_point = mount_point

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
        """Discovers and mounts the USB storage drive to mount_point.

        Raises:
            StorageNotFoundError: If no USB drive is connected.
        """
        device = self.find_usb_device()
        if not device:
            raise StorageNotFoundError(
                f"No USB storage device detected in /dev/sd*"
            )

        os.makedirs(self.mount_point, exist_ok=True)

        if os.path.ismount(self.mount_point):
            return True

        result = subprocess.run(
            ["mount", "-t", "auto", "-o", "rw", device, self.mount_point],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        if result.returncode != 0:
            raise RuntimeError(f"Failed to mount {device}: {result.stderr}")

        return True

    def unmount(self) -> bool:
        """Flushes disk buffers and unmounts the storage device cleanly."""
        # 1. Flush kernel disk buffers to hardware
        os.sync()

        # 2. Check if mounted
        if not os.path.ismount(self.mount_point):
            return True

        # 3. Unmount
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
        """Generates a standardized MP4 video file path within the storage mount."""
        if not timestamp:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        video_dir = os.path.join(self.mount_point, "videos")
        os.makedirs(video_dir, exist_ok=True)

        return os.path.join(video_dir, f"clip_{timestamp}.mp4")
