"""Master Orchestrator for Raspberry Pi Zero W Media Node.

Coordinates boot lifecycle: storage discovery, video recording,
graceful unmount, and watchdog power cutoff signaling.
"""

import argparse
import datetime
import logging
import os
import shutil
import subprocess
import sys
import time
from typing import Optional

from Pi_Zero.src.storage_manager import StorageManager, StorageNotFoundError
from Pi_Zero.src.camera_service import CameraService, CameraError
from Pi_Zero.src.watchdog_bridge import WatchdogBridge

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("MediaOrchestrator")


def _safe_float(val: object, default: Optional[float] = 0.0) -> Optional[float]:
    """Safely converts a value or mock to float, falling back to default."""
    try:
        return float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def get_system_uptime() -> Optional[float]:
    """Reads system uptime in seconds from /proc/uptime if available."""
    try:
        with open("/proc/uptime", "r") as f:
            return round(float(f.readline().split()[0]), 2)
    except (OSError, ValueError, IndexError):
        return None


def get_throttled_state() -> str:
    """Queries vcgencmd for undervoltage and throttling status flags."""
    vcgencmd = shutil.which("vcgencmd")
    if not vcgencmd:
        return "N/A"
    try:
        res = subprocess.run([vcgencmd, "get_throttled"], capture_output=True, text=True, check=False)
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return "UNKNOWN"


def resolve_lifecycle_log_path(recordings_dir: Optional[str] = None) -> str:
    """Resolves target path for lifecycle.log.

    Prioritizes the FAT boot partition (/boot/firmware, /boot, /Volumes/bootfs, /Volumes/boot)
    so the CSV log is directly accessible when the SD card is plugged into a Mac.
    Falls back to the recordings directory or current working directory.
    """
    candidates = [
        "/boot/firmware",
        "/boot",
        "/Volumes/bootfs",
        "/Volumes/boot",
    ]
    for c in candidates:
        if os.path.exists(c) and os.path.isdir(c) and os.access(c, os.W_OK):
            return os.path.join(c, "lifecycle.log")

    if recordings_dir and os.path.isdir(recordings_dir) and os.access(recordings_dir, os.W_OK):
        return os.path.join(recordings_dir, "lifecycle.log")

    return os.path.abspath("lifecycle.log")


class MediaOrchestrator:
    def __init__(
        self,
        storage_manager: Optional[StorageManager] = None,
        camera_service: Optional[CameraService] = None,
        watchdog_bridge: Optional[WatchdogBridge] = None,
        log_path: Optional[str] = None
    ):
        self.storage_manager = storage_manager or StorageManager()
        self.camera_service = camera_service or CameraService()
        self.watchdog_bridge = watchdog_bridge or WatchdogBridge()
        self.log_path = log_path

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

    def log_lifecycle_event(
        self,
        uptime_s: Optional[float],
        record_s: float,
        mux_s: float,
        total_cycle_s: float,
        status: str,
        video_file: str,
        throttled: str
    ) -> str:
        """Appends a CSV entry summarizing the cycle execution metrics.

        Returns:
            The file path where the metric entry was written.
        """
        target_path = self.log_path or resolve_lifecycle_log_path(
            getattr(self.storage_manager, "recordings_dir", None)
        )
        try:
            write_header = not os.path.exists(target_path) or os.path.getsize(target_path) == 0
            with open(target_path, "a", encoding="utf-8") as f:
                if write_header:
                    f.write("timestamp,uptime_s,record_s,mux_s,total_cycle_s,status,video_file,throttled\n")
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                uptime_val = _safe_float(uptime_s, default=None)
                uptime_str = f"{uptime_val:.2f}" if uptime_val is not None else "N/A"
                record_val = _safe_float(record_s, default=0.0) or 0.0
                mux_val = _safe_float(mux_s, default=0.0) or 0.0
                total_cycle_val = _safe_float(total_cycle_s, default=0.0) or 0.0
                f.write(
                    f"{now_str},{uptime_str},{record_val:.2f},{mux_val:.2f},"
                    f"{total_cycle_val:.2f},{status},{video_file},{throttled}\n"
                )
            logger.info(f"Lifecycle metrics logged to {target_path}")
        except Exception as e:
            logger.warning(f"Failed to append lifecycle log to {target_path}: {e}")
        return target_path

    def run_cycle(self, dry_run: bool = False) -> bool:
        """Executes the complete edge capture cycle:

        1. Discover & mount USB flash storage.
        2. Capture 20s 1080p MP4 clip from camera.
        3. Flush buffers and unmount storage.
        4. Signal shutdown acknowledgment to Arduino Nano.
        5. Halt OS.
        """
        logger.info("Starting edge capture lifecycle...")
        cycle_start = time.time()
        initial_uptime = get_system_uptime()
        status = "UNKNOWN"
        video_path = "none"

        # 1. Mount Storage
        try:
            self.storage_manager.mount()
        except StorageNotFoundError as e:
            logger.error(f"Storage unavailable: {e}. Aborting to preserve battery.")
            status = "STORAGE_ERROR"
            total_cycle_s = time.time() - cycle_start
            self.log_lifecycle_event(
                uptime_s=initial_uptime,
                record_s=0.0,
                mux_s=0.0,
                total_cycle_s=total_cycle_s,
                status=status,
                video_file="none",
                throttled=get_throttled_state()
            )
            if not dry_run and not self.is_maintenance_mode():
                self.watchdog_bridge.signal_shutdown_ack()
                self.halt_system()
            else:
                logger.info("Maintenance mode or dry-run active. Skipping watchdog shutdown ACK and system poweroff.")
            return False

        # 2. Record Video
        success = False
        try:
            throttled_state = get_throttled_state()
            video_path = self.storage_manager.generate_video_path(
                uptime_s=initial_uptime,
                throttled_state=throttled_state
            )
            logger.info(f"Target recording path: {video_path}")
            self.camera_service.record_video(video_path)
            logger.info("Video recording completed successfully.")
            status = "SUCCESS"
            success = True
        except CameraError as e:
            logger.error(f"Camera failure: {e}")
            status = "CAMERA_ERROR"
            success = False
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            status = f"ERROR_{type(e).__name__}"
            success = False
        finally:
            record_s = getattr(self.camera_service, "last_record_duration", 0.0)
            mux_s = getattr(self.camera_service, "last_mux_duration", 0.0)
            total_cycle_s = time.time() - cycle_start
            video_name = os.path.basename(video_path) if video_path and video_path != "none" else "none"

            self.log_lifecycle_event(
                uptime_s=initial_uptime,
                record_s=record_s,
                mux_s=mux_s,
                total_cycle_s=total_cycle_s,
                status=status,
                video_file=video_name,
                throttled=get_throttled_state()
            )

            # 3. Clean Filesystem Unmount (Crucial for flash lifespan)
            logger.info("Flushing disk caches and unmounting storage...")
            self.storage_manager.unmount()

            # 4. Signal Shutdown ACK to Arduino Nano & Halt System
            if dry_run or self.is_maintenance_mode():
                logger.info("Maintenance mode or dry-run active. Skipping watchdog shutdown ACK and system poweroff.")
            else:
                logger.info("Signaling shutdown ACK to Arduino Nano watchdog...")
                self.watchdog_bridge.signal_shutdown_ack()
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
