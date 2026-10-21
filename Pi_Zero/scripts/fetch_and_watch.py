#!/usr/bin/env python3
"""Fetches wildlife recordings from the Raspberry Pi Zero or directly from the SD card.

Supports:
1. Direct SD Card reading when the microSD card is inserted into a Mac card reader
   (auto-detects /Volumes/boot/Wild_Life_Recordings or /Volumes/*/Wild_Life_Recordings).
2. Remote SCP download over Wi-Fi from david@pi-zero.local into a local
   'Wild_Life_Recordings' directory.
3. Automatic containerization of raw H.264 streams into smooth QuickTime-compatible MP4s.
4. Auto-launching in QuickTime Player.

Usage:
    python3 Pi_Zero/scripts/fetch_and_watch.py
    python3 Pi_Zero/scripts/fetch_and_watch.py --pull
    python3 Pi_Zero/scripts/fetch_and_watch.py --list
    python3 Pi_Zero/scripts/fetch_and_watch.py --no-fetch
    python3 Pi_Zero/scripts/fetch_and_watch.py --host user@pi-zero.local
"""

import argparse
import datetime
import glob
import os
import shutil
import subprocess
import sys
from typing import List, Optional

HOST = "david@pi-3"
VLC_PATH = "/Applications/VLC.app/Contents/MacOS/VLC"
RECORDINGS_DIR_NAME = "Wild_Life_Recordings"

# Determine repository root
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
DEFAULT_LOCAL_DIR = os.path.join(REPO_ROOT, RECORDINGS_DIR_NAME)


def find_mounted_sd_card_dir() -> Optional[str]:
    """Scans macOS /Volumes for an inserted Raspberry Pi SD card containing Wild_Life_Recordings."""
    # Direct candidates for Raspberry Pi OS FAT boot partition
    candidates = [
        os.path.join("/Volumes/boot", RECORDINGS_DIR_NAME),
        os.path.join("/Volumes/bootfs", RECORDINGS_DIR_NAME),
    ]
    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate

    # Wildcard search for any external volume containing the directory
    for match in glob.glob(f"/Volumes/*/{RECORDINGS_DIR_NAME}"):
        if os.path.isdir(match):
            return match

    return None


import re


def parse_diagnostic_filename(filename: str) -> dict:
    """Parses sequence and diagnostic metadata from a video filename.

    Matches: clip_{SEQ:05d}_boot{UPTIME}s_{PWR}.mp4 (or .h264)
    Returns dict with 'seq', 'boot', 'power', or 'N/A' if non-matching/legacy.
    """
    base = os.path.basename(filename)
    match = re.search(r"clip_(\d+)_boot(\d+)s_([a-zA-Z0-9]+)", base)
    if match:
        return {
            "seq": match.group(1),
            "boot": f"{match.group(2)}s",
            "power": match.group(3),
        }
    return {
        "seq": "N/A",
        "boot": "N/A",
        "power": "N/A",
    }


def fetch_from_pi(
    host: str,
    dest_dir: str,
    remote_dir: Optional[str] = None,
    delete_source: bool = True,
    sync_log: bool = False,
):
    """Downloads recordings from the remote Raspberry Pi via rsync or scp.

    If delete_source is True, removes confirmed transferred recordings from the remote
    Wild_Life_Recordings directory after a successful sync.
    If sync_log is True, also syncs lifecycle.log from the Pi boot partition.
    """
    os.makedirs(dest_dir, exist_ok=True)
    rsync_bin = shutil.which("rsync")

    candidates = [remote_dir] if remote_dir else [RECORDINGS_DIR_NAME, f"SquirrelFeeder/{RECORDINGS_DIR_NAME}"]

    for candidate in candidates:
        print(f"=== Fetching recordings from {host}:~/{candidate}/ ===")
        if rsync_bin:
            print("Syncing recordings via rsync (incremental, preserves timestamps)...")
            cmd = [rsync_bin, "-avz", "--copy-links"]
            if delete_source:
                cmd.append("--remove-source-files")
            cmd.extend([f"{host}:~/{candidate}/", f"{dest_dir}/"])
            res = subprocess.run(cmd, check=False)
            if res.returncode == 0:
                print("✓ Files synced successfully via rsync.")
                if delete_source:
                    cleanup_cmd = [
                        "ssh",
                        "-o", "ConnectTimeout=5",
                        host,
                        f"rm -f ~/{candidate}/*.mp4 ~/{candidate}/*.h264 ~/{candidate}/*.mov ~/{candidate}/*.mkv 2>/dev/null || true"
                    ]
                    subprocess.run(cleanup_cmd, check=False)
                    print(f"✓ Cleaned up confirmed recordings from {host}:~/{candidate}/.")

                if sync_log:
                    log_dest = os.path.join(dest_dir, "lifecycle.log")
                    for remote_log in ["/boot/firmware/lifecycle.log", "/boot/lifecycle.log"]:
                        subprocess.run(
                            ["scp", "-p", f"{host}:{remote_log}", log_dest],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            check=False
                        )
                        if os.path.exists(log_dest):
                            print(f"✓ Synced lifecycle metrics log to {log_dest}")
                            break
                return

        # Fallback to scp command preserving timestamps
        print("Connecting via scp (enter password if prompted)...")
        cmd = ["scp", "-p", f"{host}:~/{candidate}/*", dest_dir]
        res = subprocess.run(cmd, check=False)
        if res.returncode == 0:
            print("✓ Files fetched successfully.")
            if delete_source:
                cleanup_cmd = [
                    "ssh",
                    "-o", "ConnectTimeout=5",
                    host,
                    f"rm -f ~/{candidate}/*.mp4 ~/{candidate}/*.h264 ~/{candidate}/*.mov ~/{candidate}/*.mkv 2>/dev/null || true"
                ]
                subprocess.run(cleanup_cmd, check=False)
                print(f"✓ Cleaned up confirmed recordings from {host}:~/{candidate}/.")

            if sync_log:
                log_dest = os.path.join(dest_dir, "lifecycle.log")
                for remote_log in ["/boot/firmware/lifecycle.log", "/boot/lifecycle.log"]:
                    subprocess.run(
                        ["scp", "-p", f"{host}:{remote_log}", log_dest],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False
                    )
                    if os.path.exists(log_dest):
                        print(f"✓ Synced lifecycle metrics log to {log_dest}")
                        break
            return

    print("Note: Finished attempting to fetch recordings.")


def is_mp4_container(filepath: str) -> bool:
    """Checks if the file contains an ISO MP4 ftyp atom."""
    try:
        with open(filepath, "rb") as f:
            header = f.read(32)
            return b"ftyp" in header
    except OSError:
        return False


def get_candidate_files(search_dirs: List[str], include_temp: bool = False) -> List[str]:
    """Gathers all valid video files from search directories, newest first."""
    valid_exts = {".mp4", ".h264", ".mov", ".mkv"}
    found_files = []
    seen_names = set()

    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        for entry in os.scandir(d):
            if not entry.is_file():
                continue
            name = entry.name
            # Skip hidden and macOS AppleDouble files (._*)
            if name.startswith("."):
                continue
            # Avoid duplicate listings if present across multiple search dirs
            if name in seen_names:
                continue

            ext = os.path.splitext(name)[1].lower()
            if ext in valid_exts:
                if name.endswith("_playable.mp4"):
                    continue
                # Skip 0-byte aborted files
                try:
                    if entry.stat().st_size == 0:
                        continue
                except OSError:
                    continue

                if name.endswith("_temp.h264"):
                    if not include_temp:
                        continue
                    # Check if converted MP4 already exists in any search directory
                    clean_base = name[:-10]
                    if f"{clean_base}.mp4" in seen_names or any(
                        os.path.exists(os.path.join(sd, f"{clean_base}.mp4")) for sd in search_dirs
                    ):
                        continue

                seen_names.add(name)
                found_files.append(entry.path)

    # Sort newest first, prioritizing monotonic sequence (clip_00042) then timestamp then mtime
    def sort_key(filepath: str):
        basename = os.path.basename(filepath)
        # 1. Monotonic sequence: clip_(\d+)
        seq_match = re.search(r"clip_(\d+)_", basename)
        seq_val = 0
        if seq_match:
            try:
                seq_val = int(seq_match.group(1))
            except ValueError:
                pass

        # 2. Legacy timestamp: (\d{8}_\d{6})
        ts_match = re.search(r"(\d{8}_\d{6})", basename)
        timestamp_str = ts_match.group(1) if ts_match else ""

        return (seq_val, timestamp_str, os.path.getmtime(filepath))

    found_files.sort(key=sort_key, reverse=True)
    return found_files


def package_to_smooth_mp4(input_path: str, output_path: str, fps: int = 25) -> bool:
    """Uses ffmpeg or VLC to package raw H.264 streams into QuickTime-compatible MP4s."""
    ffmpeg_bin = None
    try:
        import imageio_ffmpeg
        ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        ffmpeg_bin = shutil.which("ffmpeg")

    if ffmpeg_bin:
        print(f"Encapsulating with ffmpeg ({ffmpeg_bin})...")
        ff_cmd = [
            ffmpeg_bin,
            "-r", str(fps),
            "-i", input_path,
            "-c", "copy",
            "-y", output_path
        ]
        res = subprocess.run(
            ff_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        return res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0

    if os.path.exists(VLC_PATH):
        print(f"Encapsulating with VLC ({VLC_PATH})...")
        vlc_cmd = [
            VLC_PATH,
            "-I", "dummy",
            "--demux=h264",
            f"--h264-fps={fps}",
            input_path,
            f"--sout=#std{{access=file,mux=mp4,dst={output_path}}}",
            "vlc://quit"
        ]
        res = subprocess.run(
            vlc_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        return res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0

    return False


def sync_recordings(
    src_dir: str,
    dest_dir: str,
    convert_raw: bool = True,
    fps: int = 25,
    delete_source: bool = True,
) -> tuple:
    """Syncs recordings from src_dir to dest_dir and converts non-empty raw H.264 streams.

    Args:
        src_dir: Source directory containing recordings (e.g., mounted SD card).
        dest_dir: Local destination directory to copy/convert files into.
        convert_raw: If True, packages lingering .h264 / _temp.h264 into .mp4.
        fps: Framerate for packaging H.264 streams into MP4 container.
        delete_source: If True, deletes confirmed transferred recordings from src_dir.

    Returns:
        tuple (synced_count, converted_count)
    """
    os.makedirs(dest_dir, exist_ok=True)
    if not os.path.isdir(src_dir):
        return 0, 0

    synced_count = 0
    converted_count = 0
    deleted_count = 0

    valid_containers = {".mp4", ".mov", ".mkv"}

    try:
        entries = sorted(os.scandir(src_dir), key=lambda e: e.name)
    except OSError as e:
        print(f"[ERROR] Could not scan directory {src_dir}: {e}")
        return 0, 0

    # 1. Copy containerized files (.mp4, .mov, .mkv)
    for entry in entries:
        name = entry.name
        if not entry.is_file() or name.startswith("."):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext in valid_containers:
            dest_path = os.path.join(dest_dir, name)
            # Only copy if file does not exist or size differs
            if not os.path.exists(dest_path) or os.path.getsize(dest_path) != entry.stat().st_size:
                size_mb = entry.stat().st_size / (1024 * 1024)
                print(f"  Copying: {name} ({size_mb:.2f} MB)...")
                shutil.copy2(entry.path, dest_path)
                synced_count += 1

            # Confirm file exists and size matches in destination before deleting from source
            if delete_source and os.path.exists(dest_path) and os.path.getsize(dest_path) == entry.stat().st_size:
                try:
                    os.remove(entry.path)
                    deleted_count += 1
                    apple_double = os.path.join(src_dir, f"._{name}")
                    if os.path.exists(apple_double):
                        os.remove(apple_double)
                except OSError as e:
                    print(f"  [WARNING] Could not delete source file {entry.path}: {e}")

    # 2. Convert non-empty raw streams (.h264, _temp.h264)
    if convert_raw:
        for entry in entries:
            name = entry.name
            if not entry.is_file() or name.startswith("."):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext == ".h264":
                try:
                    size = entry.stat().st_size
                except OSError:
                    continue
                if size == 0:
                    if delete_source:
                        try:
                            os.remove(entry.path)
                        except OSError:
                            pass
                    continue

                if name.endswith("_temp.h264"):
                    clean_base = name[:-10]
                    target_name = f"{clean_base}.mp4"
                else:
                    base = os.path.splitext(name)[0]
                    target_name = f"{base}.mp4"

                dest_mp4 = os.path.join(dest_dir, target_name)
                converted = False
                # If target mp4 already exists and is non-empty, skip
                if not (os.path.exists(dest_mp4) and os.path.getsize(dest_mp4) > 0):
                    size_mb = size / (1024 * 1024)
                    print(f"  Packaging raw stream: {name} ({size_mb:.2f} MB) -> {target_name}...")
                    if package_to_smooth_mp4(entry.path, dest_mp4, fps=fps):
                        print(f"  ✓ Converted to {target_name}")
                        converted_count += 1
                        converted = True
                    else:
                        print(f"  [WARNING] Failed to convert {name} to MP4")
                else:
                    converted = True

                # Confirm destination MP4 exists and is non-empty before deleting raw source
                if delete_source and converted and os.path.exists(dest_mp4) and os.path.getsize(dest_mp4) > 0:
                    try:
                        os.remove(entry.path)
                        deleted_count += 1
                        apple_double = os.path.join(src_dir, f"._{name}")
                        if os.path.exists(apple_double):
                            os.remove(apple_double)
                    except OSError as e:
                        print(f"  [WARNING] Could not delete source file {entry.path}: {e}")

    if delete_source and deleted_count > 0:
        print(f"  ✓ Cleaned up {deleted_count} transferred recording(s) from SD card.")

    # 3. Also sync lifecycle.log if present in src_dir or parent volume
    log_candidates = [
        os.path.join(src_dir, "lifecycle.log"),
        os.path.join(os.path.dirname(src_dir), "lifecycle.log"),
    ]
    for log_c in log_candidates:
        if os.path.exists(log_c) and os.path.isfile(log_c):
            dest_log = os.path.join(dest_dir, "lifecycle.log")
            if not os.path.exists(dest_log) or os.path.getmtime(log_c) > os.path.getmtime(dest_log):
                print(f"  ✓ Synced lifecycle metrics log to: {dest_log}")
                shutil.copy2(log_c, dest_log)
            break

    return synced_count, converted_count


def convert_lingering_raw_streams(directory: str, fps: int = 25) -> int:
    """Finds non-empty .h264 streams in directory and converts them to MP4 if missing."""
    if not os.path.isdir(directory):
        return 0

    converted_count = 0
    try:
        entries = sorted(os.scandir(directory), key=lambda e: e.name)
    except OSError:
        return 0

    for entry in entries:
        name = entry.name
        if not entry.is_file() or name.startswith("."):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext == ".h264":
            try:
                size = entry.stat().st_size
            except OSError:
                continue
            if size == 0:
                continue

            if name.endswith("_temp.h264"):
                clean_base = name[:-10]
                target_name = f"{clean_base}.mp4"
            else:
                base = os.path.splitext(name)[0]
                target_name = f"{base}.mp4"

            dest_mp4 = os.path.join(directory, target_name)
            if os.path.exists(dest_mp4) and os.path.getsize(dest_mp4) > 0:
                continue

            size_mb = size / (1024 * 1024)
            print(f"  Packaging raw stream: {name} ({size_mb:.2f} MB) -> {target_name}...")
            if package_to_smooth_mp4(entry.path, dest_mp4, fps=fps):
                print(f"  ✓ Converted to {target_name}")
                converted_count += 1
                try:
                    os.remove(entry.path)
                except OSError:
                    pass

    return converted_count


def list_recordings(files: List[str]):
    """Prints a formatted summary of available recordings."""
    if not files:
        print("No recordings found.")
        return

    print("\n" + "=" * 92)
    print(f"  {'SEQ':<7} {'FILENAME':<38} {'BOOT':<7} {'POWER':<9} {'SIZE (MB)':<11} {'MODIFIED'}")
    print("=" * 92)
    for f in files:
        size_mb = os.path.getsize(f) / (1024 * 1024)
        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d %H:%M:%S")
        diag = parse_diagnostic_filename(f)
        seq_str = diag["seq"]
        boot_str = diag["boot"]
        pwr_str = diag["power"]
        fname = os.path.basename(f)
        if len(fname) > 37:
            fname = fname[:34] + "..."
        print(f"  {seq_str:<7} {fname:<38} {boot_str:<7} {pwr_str:<9} {size_mb:>8.2f} MB   {mtime}")
    print("=" * 92 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Fetch and watch wildlife recordings from Raspberry Pi Zero or mounted SD Card."
    )
    parser.add_argument(
        "--sync", "--pull",
        dest="sync",
        action="store_true",
        help="Pull and sync all recordings from SD card (or remote Pi) to local Wild_Life_Recordings directory, and convert non-empty raw .h264 streams to MP4."
    )
    parser.add_argument(
        "--host",
        type=str,
        default=HOST,
        help=f"Pi Zero SSH host (default: {HOST})"
    )
    parser.add_argument(
        "-d", "--dir",
        type=str,
        default=None,
        help="Specify custom directory containing recordings"
    )
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="Skip remote SCP fetch; inspect local directory or mounted SD card only"
    )
    parser.add_argument(
        "--force-fetch",
        action="store_true",
        help="Force remote SCP fetch even if a local SD card is detected"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all recordings found and exit"
    )
    parser.add_argument(
        "--no-open", "--no-watch",
        dest="no_open",
        action="store_true",
        help="Do not open video in QuickTime Player after fetching/syncing."
    )
    parser.add_argument(
        "--remote-dir",
        type=str,
        default=None,
        help="Optional remote directory path on the Pi (e.g. SquirrelFeeder/Wild_Life_Recordings)"
    )
    parser.add_argument(
        "-f", "--file",
        type=str,
        default=None,
        help="Open a specific video file path instead of newest"
    )
    parser.add_argument(
        "--keep", "--no-delete",
        dest="delete_source",
        action="store_false",
        default=True,
        help="Keep source recordings in Wild_Life_Recordings after transferring (default: delete confirmed transferred files)."
    )

    args = parser.parse_args()

    sd_card_dir = find_mounted_sd_card_dir()
    local_dir = os.path.abspath(args.dir) if args.dir else DEFAULT_LOCAL_DIR
    os.makedirs(local_dir, exist_ok=True)

    active_dir = None

    if args.dir:
        active_dir = local_dir
    elif args.sync:
        if sd_card_dir and not args.force_fetch:
            print(f"✓ Found Raspberry Pi SD Card mounted at: {sd_card_dir}")
            print(f"Syncing recordings from SD card to local directory ({local_dir})...")
            synced_count, converted_count = sync_recordings(
                sd_card_dir, local_dir, delete_source=args.delete_source
            )
            print(f"✓ Sync complete: {synced_count} file(s) copied, {converted_count} raw stream(s) converted to MP4.\n")
            active_dir = local_dir
        else:
            active_dir = local_dir
            if not args.no_fetch:
                fetch_from_pi(
                    host=args.host, dest_dir=local_dir, remote_dir=args.remote_dir, delete_source=args.delete_source, sync_log=True
                )
            converted_count = convert_lingering_raw_streams(local_dir)
            if converted_count > 0:
                print(f"✓ Converted {converted_count} lingering raw stream(s) to MP4.\n")
    elif sd_card_dir and not args.force_fetch:
        print(f"✓ Found Raspberry Pi SD Card mounted at: {sd_card_dir}")
        print("Reading recordings directly from SD Card without network overhead!")
        print("Tip: Run with --pull (or --sync) to copy all SD card clips locally and convert raw streams.\n")
        active_dir = sd_card_dir
    else:
        active_dir = local_dir
        if not args.no_fetch and not args.list:
            fetch_from_pi(
                host=args.host, dest_dir=local_dir, remote_dir=args.remote_dir, delete_source=args.delete_source, sync_log=True
            )
            convert_lingering_raw_streams(local_dir)

    # Search directories for candidate video files
    search_dirs = [active_dir]
    if active_dir != local_dir and os.path.isdir(local_dir):
        search_dirs.append(local_dir)
    # Also check repo root for any legacy recordings
    if os.path.isdir(REPO_ROOT):
        search_dirs.append(REPO_ROOT)

    candidates = get_candidate_files(search_dirs, include_temp=True)

    if args.list:
        list_recordings(candidates)
        return

    target_video = None
    if args.file:
        if os.path.exists(args.file):
            target_video = os.path.abspath(args.file)
        else:
            print(f"[ERROR] Specified file not found: {args.file}")
            sys.exit(1)
    else:
        if not candidates:
            print("\n[ERROR] No video recordings found.")
            print(f"Checked directories: {', '.join(search_dirs)}")
            print("Please check that the camera has recorded clips or run with --host.")
            sys.exit(1)
        target_video = candidates[0]

    size_mb = os.path.getsize(target_video) / (1024 * 1024)
    print(f"Target recording: {target_video} ({size_mb:.2f} MB)")

    if is_mp4_container(target_video):
        if not args.no_open:
            print("File is a valid MP4 container. Launching in QuickTime Player...")
            subprocess.run(["open", target_video])
            print("✓ Opened in QuickTime Player!")
        else:
            print(f"File is a valid MP4 container: {target_video}")
    else:
        print("Raw H.264 stream detected. Packaging into QuickTime-compatible MP4 container...")
        base_name = os.path.splitext(os.path.basename(target_video))[0]
        clean_name = base_name[:-5] if base_name.endswith("_temp") else base_name
        output_mp4 = os.path.join(local_dir, f"{clean_name}.mp4")
        if os.path.exists(output_mp4) and os.path.getsize(output_mp4) > 0 and output_mp4 != target_video:
            output_mp4 = os.path.join(local_dir, f"{clean_name}_smooth.mp4")

        success = package_to_smooth_mp4(target_video, output_mp4, fps=25)
        if success:
            print(f"✓ Smooth MP4 created: {output_mp4}")
            if not args.no_open:
                subprocess.run(["open", output_mp4])
                print("✓ Opened in QuickTime Player!")
        else:
            print("[WARNING] Could not package to MP4. Attempting to launch in VLC...")
            if not args.no_open:
                subprocess.run(["open", "-a", "VLC", target_video])


if __name__ == "__main__":
    main()

