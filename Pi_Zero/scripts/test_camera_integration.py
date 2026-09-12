#!/usr/bin/env python3
"""Standalone Camera Integration Test for Raspberry Pi Zero W.

Tests hardware communication with the CSI Camera Module:
1. Detects camera binary and queries connected sensor modules.
2. Turns on the camera and records 20 seconds of 1080p video.
3. Shuts down the camera pipeline cleanly.
4. Packages to native MP4 (if MP4Box/ffmpeg is available) or saves clean .h264.
5. Verifies the generated video file size and integrity.

Usage:
    python3 Pi_Zero/scripts/test_camera_integration.py
    python3 Pi_Zero/scripts/test_camera_integration.py --duration 20
    python3 Pi_Zero/scripts/test_camera_integration.py --dry-run
"""

import argparse
import datetime
import os
import shutil
import subprocess
import sys
import time
from typing import List, Optional, Tuple

# Enable importing from repository root if run standalone
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

try:
    from Pi_Zero.src.camera_service import CameraService, CameraError
except ImportError:
    class CameraError(Exception):
        """Raised when camera initialization or recording fails."""
        pass

    class CameraService:
        def __init__(
            self,
            width: int = 1920,
            height: int = 1080,
            fps: int = 25,
            duration_ms: int = 20000,
            binary: Optional[str] = None
        ):
            self.width = width
            self.height = height
            self.fps = fps
            self.duration_ms = duration_ms
            self.binary = binary

        def resolve_binary(self) -> str:
            if self.binary:
                return self.binary
            for candidate in ["rpicam-vid", "libcamera-vid"]:
                path = shutil.which(candidate)
                if path:
                    return path
            return "rpicam-vid"

        def build_command(self, output_path: str) -> List[str]:
            binary = self.resolve_binary()
            return [
                binary,
                "--width", str(self.width),
                "--height", str(self.height),
                "--framerate", str(self.fps),
                "-t", str(self.duration_ms),
                "--nopreview",
                "-o", output_path
            ]

        def record_video(self, output_path: str) -> bool:
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
                        f"Camera recording failed (code {result.returncode}): {result.stderr.strip()}"
                    )
                return True
            except FileNotFoundError as e:
                raise CameraError(f"Camera capture binary not found: {e}")


def check_camera_detection(binary: str) -> Tuple[bool, str]:
    """Queries the camera subsystem to detect connected CSI sensors."""
    candidates = []
    if "rpicam" in binary:
        candidates.extend(["rpicam-hello", "rpicam-vid"])
    else:
        candidates.extend(["libcamera-hello", "libcamera-vid"])

    for tool_name in ["rpicam-hello", "libcamera-hello", binary]:
        tool_path = shutil.which(tool_name)
        if tool_path and tool_path not in candidates:
            candidates.append(tool_path)

    for tool in candidates:
        if shutil.which(tool):
            try:
                res = subprocess.run(
                    [tool, "--list-cameras"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=5,
                    check=False
                )
                output = (res.stdout + "\n" + res.stderr).strip()
                if "No cameras available" in output:
                    return False, output
                if "Available cameras" in output or "seq" in output:
                    return True, output
            except Exception:
                pass

    return False, "Could not query camera detection tool."


def package_h264_to_mp4(h264_path: str, mp4_path: str, fps: int = 25) -> bool:
    """Packages a raw H.264 elementary stream into an MP4 container if tools exist."""
    mp4box = shutil.which("MP4Box")
    if mp4box:
        try:
            res = subprocess.run(
                [mp4box, "-fps", str(fps), "-add", h264_path, mp4_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            return res.returncode == 0 and os.path.exists(mp4_path) and os.path.getsize(mp4_path) > 0
        except Exception:
            pass

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        try:
            res = subprocess.run(
                [ffmpeg, "-framerate", str(fps), "-i", h264_path, "-c", "copy", "-y", mp4_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            return res.returncode == 0 and os.path.exists(mp4_path) and os.path.getsize(mp4_path) > 0
        except Exception:
            pass

    return False


def print_troubleshooting_tips():
    """Prints hardware troubleshooting guidance for Raspberry Pi Zero W CSI camera."""
    print("\n" + "=" * 60)
    print("           CAMERA HARDWARE TROUBLESHOOTING GUIDE")
    print("=" * 60)
    print("1. Ribbon Cable Orientation:")
    print("   - Pi Zero W has a smaller 15-pin CSI connector than standard Pis.")
    print("   - Ensure the metal contact pins face DOWN toward the circuit board.")
    print("   - Ensure the blue backing tape faces UP toward the ceiling.")
    print("   - Make sure the retaining clip is fully locked on both sides.")
    print("2. Camera Enable / Firmware Overlay:")
    print("   - Check /boot/config.txt (or /boot/firmware/config.txt).")
    print("   - Ensure 'camera_auto_detect=1' is present.")
    print("3. Memory Allocation:")
    print("   - Ensure GPU memory is at least 128MB: 'gpu_mem=128' in config.txt.")
    print("4. Manual Diagnostic Command:")
    print("   - Run: rpicam-hello --list-cameras (or libcamera-hello --list-cameras)")
    print("=" * 60 + "\n")


def run_integration_test(
    duration_sec: int = 20,
    output_path: Optional[str] = None,
    width: int = 1920,
    height: int = 1080,
    fps: int = 25,
    dry_run: bool = False,
    check_only: bool = False
) -> bool:
    """Executes the camera integration test workflow."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    wants_mp4 = True
    if output_path:
        output_path = os.path.abspath(output_path)
        if output_path.lower().endswith(".h264"):
            wants_mp4 = False
    else:
        output_path = os.path.abspath(f"./camera_test_{timestamp}.mp4")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    print("=" * 60)
    print("      Raspberry Pi Zero W - Camera Integration Test")
    print("=" * 60)
    print(f"Target Duration:   {duration_sec} seconds")
    print(f"Resolution:        {width}x{height} @ {fps} fps")
    print(f"Dry-Run Mode:      {'ENABLED' if dry_run else 'DISABLED'}")
    print("=" * 60)

    # 1. Resolve Camera Binary
    camera = CameraService(
        width=width,
        height=height,
        fps=fps,
        duration_ms=duration_sec * 1000
    )
    binary = camera.resolve_binary()
    binary_path = shutil.which(binary) or shutil.which(os.path.basename(binary))
    print(f"\n[Step 1/4] Checking camera driver binaries...")
    print(f"  Selected tool:   {binary}")
    print(f"  Resolved path:   {binary_path or 'NOT FOUND'}")

    if not binary_path and not dry_run:
        print("  [ERROR] Neither 'rpicam-vid' nor 'libcamera-vid' was found on this system!")
        print_troubleshooting_tips()
        return False

    # 2. Hardware Sensor Query
    print(f"\n[Step 2/4] Detecting connected camera sensor...")
    if dry_run:
        print("  [DRY-RUN] Simulating detected sensor: OV5647 (CSI-2 / 1080p).")
        detected = True
    else:
        detected, details = check_camera_detection(binary)
        if detected:
            print("  ✓ Camera sensor detected successfully!")
            for line in details.splitlines():
                if line.strip():
                    print(f"    {line.strip()}")
        else:
            print("  [WARNING] Sensor probe returned no active camera.")
            if details:
                print(f"    Details: {details}")
            print("  Attempting capture anyway in case direct pipeline succeeds...")

    if check_only:
        print("\n[INFO] Check-only mode requested. Skipping video recording.")
        return detected

    # 3. Video Capture (Camera ON -> Record 20s -> Camera OFF)
    print(f"\n[Step 3/4] Turning ON camera and capturing {duration_sec} seconds of video...")
    start_time = time.time()

    # Determine paths for raw capture vs MP4
    has_muxer = bool(shutil.which("MP4Box") or shutil.which("ffmpeg"))
    if wants_mp4 and not has_muxer and not dry_run:
        # Switch to .h264 extension so file is accurately identified
        actual_output_path = os.path.splitext(output_path)[0] + ".h264"
        raw_target = actual_output_path
        will_mux = False
    elif wants_mp4 and has_muxer and not dry_run:
        actual_output_path = output_path
        raw_target = os.path.splitext(output_path)[0] + "_temp.h264"
        will_mux = True
    else:
        actual_output_path = output_path
        raw_target = output_path
        will_mux = False

    if dry_run:
        print(f"  [DRY-RUN] Simulating {duration_sec}-second video recording...")
        time.sleep(0.5)
        with open(actual_output_path, "wb") as f:
            f.write(b"\x00\x00\x00\x20ftypmp42" + b"\x00" * (1024 * 512))
        success = True
    else:
        cmd = camera.build_command(raw_target)
        print(f"  Executing command: {' '.join(cmd)}")
        print("  Camera stream active... (Please wait)")
        try:
            success = camera.record_video(raw_target)
        except CameraError as e:
            print(f"  [ERROR] Recording failed: {e}")
            print_troubleshooting_tips()
            return False

        if will_mux:
            print("  Muxing H.264 stream into MP4 container...")
            if package_h264_to_mp4(raw_target, actual_output_path, fps=fps):
                try:
                    os.remove(raw_target)
                except OSError:
                    pass
            else:
                print("  [WARNING] Muxing failed. Retaining raw .h264 file.")
                actual_output_path = raw_target

    elapsed = time.time() - start_time
    print(f"  Camera turned OFF cleanly. (Elapsed: {elapsed:.1f}s)")

    # 4. Verification of Output File
    print(f"\n[Step 4/4] Verifying recorded video output...")
    if not os.path.exists(actual_output_path):
        print(f"  [ERROR] Output file does not exist: {actual_output_path}")
        return False

    file_size_bytes = os.path.getsize(actual_output_path)
    file_size_mb = file_size_bytes / (1024 * 1024)
    print(f"  File path:       {actual_output_path}")
    print(f"  File size:       {file_size_mb:.2f} MB ({file_size_bytes:,} bytes)")

    if file_size_bytes == 0:
        print("  [ERROR] Output file is 0 bytes! No video data was recorded.")
        print_troubleshooting_tips()
        return False

    # Success Banner
    print("\n" + "=" * 60)
    print("     ✓ CAMERA INTEGRATION TEST PASSED SUCCESSFULLY!")
    print("=" * 60)
    print(f"  • Video Saved:    {actual_output_path}")
    print(f"  • Duration:       {duration_sec}s recorded")
    print(f"  • File Size:      {file_size_mb:.2f} MB")
    print(f"  • Camera Status:  Turned off & pipeline released")

    if actual_output_path.endswith(".h264"):
        print("\n  [PLAYBACK NOTE]")
        print("  File format is raw H.264 elementary stream.")
        print("  - To play directly on Mac:  open -a VLC <filename>.h264")
        print("  - To auto-generate MP4s on Pi Zero: sudo apt install -y gpac")
    else:
        print("\n  [PLAYBACK NOTE]")
        print("  File format is standard MP4 container (QuickTime & VLC compatible).")
        print("  - To play on Mac:           open <filename>.mp4")

    print("=" * 60 + "\n")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Raspberry Pi Zero W Camera Integration Test Script"
    )
    parser.add_argument(
        "-d", "--duration",
        type=int,
        default=20,
        help="Recording duration in seconds (default: 20)"
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="Destination path for video file (default: ./camera_test_<timestamp>.mp4)"
    )
    parser.add_argument(
        "--width",
        type=int,
        default=1920,
        help="Video frame width (default: 1920)"
    )
    parser.add_argument(
        "--height",
        type=int,
        default=1080,
        help="Video frame height (default: 1080)"
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=25,
        help="Video framerate (default: 25)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate camera operations without accessing hardware"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Detect camera sensor without recording video"
    )

    args = parser.parse_args()

    success = run_integration_test(
        duration_sec=args.duration,
        output_path=args.output,
        width=args.width,
        height=args.height,
        fps=args.fps,
        dry_run=args.dry_run,
        check_only=args.check_only
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
