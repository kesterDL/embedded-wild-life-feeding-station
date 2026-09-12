#!/usr/bin/env python3
"""Fetches the latest camera test video from the Raspberry Pi Zero and opens it in QuickTime.

Handles both containerized MP4 and raw H.264 elementary streams by automatically
packaging raw streams via VLC on macOS.

Usage:
    python3 scripts/fetch_and_watch.py
"""

import glob
import os
import shutil
import subprocess
import sys

HOST = "david@pi-zero.local"
VLC_PATH = "/Applications/VLC.app/Contents/MacOS/VLC"


def fetch_from_pi(host: str = HOST):
    print(f"=== Fetching test recordings from {host} ===")
    print("Connecting via scp (enter password if prompted)...")
    # Fetch any camera test files (.h264, .mp4, etc.)
    cmd = ["scp", f"{host}:~/camera_test_*", "."]
    subprocess.run(cmd, check=False)


def is_mp4_container(filepath: str) -> bool:
    """Checks if the file contains an ISO MP4 ftyp atom."""
    try:
        with open(filepath, "rb") as f:
            header = f.read(32)
            return b"ftyp" in header
    except OSError:
        return False


def main():
    fetch_from_pi()

    # Find all camera_test files in current directory
    candidates = glob.glob("camera_test_*")
    # Exclude temporary or intermediate files
    valid_files = [
        f for f in candidates
        if not f.endswith("_temp.h264")
        and not f.endswith("_playable.mp4")
    ]

    if not valid_files:
        print("\n[ERROR] No camera_test_* files found in current directory.")
        print("Please check that the test script ran on the Pi Zero.")
        sys.exit(1)

    # Sort by modification time, newest first
    valid_files.sort(key=os.path.getmtime, reverse=True)
    latest = valid_files[0]
    print(f"\nLatest recording: {latest} ({os.path.getsize(latest) / (1024*1024):.2f} MB)")

    if is_mp4_container(latest):
        print("File is a valid MP4 container. Launching in QuickTime Player...")
        subprocess.run(["open", latest])
        print("✓ Opened in QuickTime Player!")
    else:
        print("Raw H.264 stream detected. Packaging into QuickTime-compatible MP4 container...")
        base_name = os.path.splitext(latest)[0]
        output_mp4 = f"{base_name}_smooth.mp4"

        # Try ffmpeg first (preserves exact 25/30 fps timestamps without jitter)
        ffmpeg_bin = None
        try:
            import imageio_ffmpeg
            ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            ffmpeg_bin = shutil.which("ffmpeg")

        if ffmpeg_bin:
            print(f"Encapsulating with ffmpeg ({ffmpeg_bin})...")
            # Use -r 25 (or 30) to establish constant frame rate and valid PTS timestamps
            ff_cmd = [
                ffmpeg_bin,
                "-r", "25",
                "-i", latest,
                "-c", "copy",
                "-y", output_mp4
            ]
            res = subprocess.run(
                ff_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            if res.returncode == 0 and os.path.exists(output_mp4) and os.path.getsize(output_mp4) > 0:
                print(f"✓ Smooth MP4 created: {output_mp4}")
                subprocess.run(["open", output_mp4])
                print("✓ Opened in QuickTime Player!")
                return

        if os.path.exists(VLC_PATH):
            vlc_cmd = [
                VLC_PATH,
                "-I", "dummy",
                "--demux=h264",
                "--h264-fps=25",
                latest,
                f"--sout=#std{{access=file,mux=mp4,dst={output_mp4}}}",
                "vlc://quit"
            ]
            subprocess.run(
                vlc_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            if os.path.exists(output_mp4) and os.path.getsize(output_mp4) > 0:
                print(f"✓ Packaged to: {output_mp4}")
                subprocess.run(["open", output_mp4])
                print("✓ Opened in QuickTime Player!")
            else:
                print(f"[WARNING] Packaging failed. Opening in VLC directly...")
                subprocess.run(["open", "-a", "VLC", latest])
        else:
            print("VLC/ffmpeg not found for muxing. Opening raw file in VLC...")
            subprocess.run(["open", "-a", "VLC", latest])


if __name__ == "__main__":
    main()
