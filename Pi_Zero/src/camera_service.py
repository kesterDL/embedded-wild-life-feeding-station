"""Camera Service for Raspberry Pi Zero W.

Controls CSI Camera Module via rpicam-vid / libcamera-vid to capture
hardware-encoded 1080p H.264 video packaged into MP4.
"""

import shutil
import subprocess
from typing import List, Optional


class CameraError(Exception):
    """Raised when camera initialization or recording fails."""
    pass


class CameraService:
    def __init__(
        self,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        duration_ms: int = 20000,
        binary: Optional[str] = None
    ):
        self.width = width
        self.height = height
        self.fps = fps
        self.duration_ms = duration_ms
        self.binary = binary

    def resolve_binary(self) -> str:
        """Determines whether rpicam-vid or legacy libcamera-vid is present."""
        if self.binary:
            return self.binary

        for candidate in ["rpicam-vid", "libcamera-vid"]:
            path = shutil.which(candidate)
            if path:
                return path

        return "rpicam-vid"

    def build_command(self, output_path: str) -> List[str]:
        """Constructs the command line arguments for the camera capture tool."""
        binary = self.resolve_binary()
        cmd = [
            binary,
            "--width", str(self.width),
            "--height", str(self.height),
            "--framerate", str(self.fps),
            "-t", str(self.duration_ms),
            "--nopreview",
            "-o", output_path
        ]
        return cmd

    def record_video(self, output_path: str) -> bool:
        """Executes the video recording subprocess.

        Raises:
            CameraError: If the recording process fails or returns non-zero.
        """
        cmd = self.build_command(output_path)
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            if result.returncode != 0:
                raise CameraError(
                    f"Camera recording failed (code {result.returncode}): {result.stderr}"
                )
            return True
        except FileNotFoundError as e:
            raise CameraError(f"Camera capture binary not found: {e}")
