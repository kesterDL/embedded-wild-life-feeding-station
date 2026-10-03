"""Master Orchestrator for Raspberry Pi Zero W Media Node.

Coordinates boot lifecycle: storage discovery, video recording,
graceful unmount, and watchdog power cutoff signaling.
"""

import argparse
import logging
import os
import subprocess
import sys
from typing import Optional

from Pi_Zero.src.storage_manager import StorageManager, StorageNotFoundError
from Pi_Zero.src.camera_service import CameraService, CameraError
from Pi_Zero.src.watchdog_bridge import WatchdogBridge

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("MediaOrchestrator")


class MediaOrchestrator:
    def __init__(
        self,
        storage_manager: Optional[StorageManager] = None,
        camera_service: Optional[CameraService] = None,
        watchdog_bridge: Optional[WatchdogBridge] = None
    ):
        self.storage_manager = storage_manager or StorageManager()
        self.camera_service = camera_service or CameraService()
        self.watchdog_bridge = watchdog_bridge or WatchdogBridge()

    def halt_system(self) -> None:
        """Executes clean OS poweroff."""
        logger.info("Executing system poweroff...")
        try:
            subprocess.run(["poweroff"], check=False)
        except Exception as e:
            logger.error(f"Failed to execute poweroff: {e}")

    def is_maintenance_mode(self) -> bool:
        """Checks if a maintenance flag file exists to prevent automatic poweroff.

        Allows developers to prevent shutdown by simply creating an empty file named
        'maintenance' or 'no_shutdown' on the SD card boot partition or in Wild_Life_Recordings.
        """
        candidate_paths = [
            "/boot/firmware/maintenance",
            "/boot/firmware/no_shutdown",
            "/boot/maintenance",
            "/boot/no_shutdown",
            "/Volumes/bootfs/maintenance",
            "/Volumes/boot/maintenance",
            os.path.join(getattr(self.storage_manager, "recordings_dir", ""), "maintenance"),
            os.path.join(getattr(self.storage_manager, "recordings_dir", ""), "no_shutdown")
        ]
        return any(os.path.exists(p) for p in candidate_paths if p)

    def run_cycle(self, dry_run: bool = False) -> bool:
        """Executes the complete edge capture cycle:

        1. Discover & mount USB flash storage.
        2. Capture 20s 1080p MP4 clip from camera.
        3. Flush buffers and unmount storage.
        4. Signal shutdown acknowledgment to Arduino Nano.
        5. Halt OS.
        """
        logger.info("Starting edge capture lifecycle...")

        # 1. Mount Storage
        try:
            self.storage_manager.mount()
        except StorageNotFoundError as e:
            logger.error(f"Storage unavailable: {e}. Aborting to preserve battery.")
            self.watchdog_bridge.signal_shutdown_ack()
            if not dry_run and not self.is_maintenance_mode():
                self.halt_system()
            return False

        # 2. Record Video
        success = False
        try:
            video_path = self.storage_manager.generate_video_path()
            logger.info(f"Target recording path: {video_path}")
            self.camera_service.record_video(video_path)
            logger.info("Video recording completed successfully.")
            success = True
        except CameraError as e:
            logger.error(f"Camera failure: {e}")
            success = False
        finally:
            # 3. Clean Filesystem Unmount (Crucial for flash lifespan)
            logger.info("Flushing disk caches and unmounting storage...")
            self.storage_manager.unmount()

            # 4. Signal Shutdown ACK to Arduino Nano
            logger.info("Signaling shutdown ACK to Arduino Nano watchdog...")
            self.watchdog_bridge.signal_shutdown_ack()

            # 5. Halt System
            if dry_run or self.is_maintenance_mode():
                logger.info("Maintenance mode or dry-run active. Skipping system poweroff.")
            else:
                self.halt_system()

        return success



def main():
    parser = argparse.ArgumentParser(description="Squirrel Feeder Media Orchestrator")
    parser.add_argument("--dry-run", action="store_true", help="Run without calling poweroff")
    args = parser.parse_args()

    orchestrator = MediaOrchestrator()
    result = orchestrator.run_cycle(dry_run=args.dry_run)
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
