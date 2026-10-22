import os
import subprocess
import unittest
from unittest.mock import patch, MagicMock
from Pi_Zero.src.storage_manager import StorageManager, StorageNotFoundError


class TestStorageManager(unittest.TestCase):

    def setUp(self):
        self.sm = StorageManager(mount_point="/mnt/usb_storage")

    @patch("glob.glob")
    def test_find_usb_device_partition_priority(self, mock_glob):
        # Partitions like /dev/sda1 should take precedence over whole-disk /dev/sda
        mock_glob.side_effect = lambda pattern: (
            ["/dev/sda1"] if "sd[a-z][0-9]" in pattern else ["/dev/sda"]
        )
        device = self.sm.find_usb_device()
        self.assertEqual(device, "/dev/sda1")

    @patch("glob.glob")
    def test_find_usb_device_raw_fallback(self, mock_glob):
        # If no partitioned /dev/sd* exists, fall back to /dev/sda
        mock_glob.side_effect = lambda pattern: (
            [] if "sd[a-z][0-9]" in pattern else ["/dev/sda"]
        )
        device = self.sm.find_usb_device()
        self.assertEqual(device, "/dev/sda")

    @patch("glob.glob")
    def test_find_usb_device_none_found(self, mock_glob):
        mock_glob.return_value = []
        device = self.sm.find_usb_device()
        self.assertIsNone(device)

    @patch("glob.glob")
    @patch("os.path.ismount")
    @patch("os.makedirs")
    @patch("subprocess.run")
    def test_mount_success(self, mock_run, mock_makedirs, mock_ismount, mock_glob):
        mock_glob.return_value = ["/dev/sda1"]
        mock_ismount.return_value = False
        mock_run.return_value = MagicMock(returncode=0)

        result = self.sm.mount()
        self.assertTrue(result)
        mock_makedirs.assert_any_call("/mnt/usb_storage", exist_ok=True)
        mock_makedirs.assert_any_call("/mnt/usb_storage/Wild_Life_Recordings", exist_ok=True)
        mock_run.assert_called()
        cmd = mock_run.call_args[0][0]
        self.assertIn("mount", cmd)
        self.assertIn("/dev/sda1", cmd)
        self.assertIn("/mnt/usb_storage", cmd)

    @patch("glob.glob")
    def test_mount_missing_device_raises_exception(self, mock_glob):
        mock_glob.return_value = []
        with self.assertRaises(StorageNotFoundError):
            self.sm.mount()

    @patch("os.sync")
    @patch("subprocess.run")
    @patch("os.path.ismount")
    def test_unmount_calls_sync_and_umount(self, mock_ismount, mock_run, mock_sync):
        mock_ismount.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        result = self.sm.unmount()
        self.assertTrue(result)
        mock_sync.assert_called_once()
        mock_run.assert_called()
        cmd = mock_run.call_args[0][0]
        self.assertIn("umount", cmd)
        self.assertIn("/mnt/usb_storage", cmd)

    @patch("os.makedirs")
    def test_generate_video_path_diagnostic_format_ok(self, mock_makedirs):
        # Format: clip_{SEQ:05d}_boot{UPTIME}s_{PWR}.mp4
        path = self.sm.generate_video_path(uptime_s=16.48, throttled_state="throttled=0x0", seq=42)
        expected_path = "/mnt/usb_storage/Wild_Life_Recordings/clip_00042_boot16s_pwrOK.mp4"
        self.assertEqual(path, expected_path)
        mock_makedirs.assert_called_with("/mnt/usb_storage/Wild_Life_Recordings", exist_ok=True)

    @patch("os.makedirs")
    def test_generate_video_path_diagnostic_format_warning(self, mock_makedirs):
        # When throttled is non-zero (undervoltage / throttling), PWR flag is pwrWARN
        path = self.sm.generate_video_path(uptime_s=17.8, throttled_state="throttled=0x50005", seq=43)
        expected_path = "/mnt/usb_storage/Wild_Life_Recordings/clip_00043_boot18s_pwrWARN.mp4"
        self.assertEqual(path, expected_path)

    @patch("os.makedirs")
    def test_generate_video_path_diagnostic_format_default_args(self, mock_makedirs):
        # Should gracefully handle missing/None uptime or throttled state
        path = self.sm.generate_video_path(uptime_s=None, throttled_state=None, seq=1)
        expected_path = "/mnt/usb_storage/Wild_Life_Recordings/clip_00001_boot0s_pwrOK.mp4"
        self.assertEqual(path, expected_path)

    def test_sequence_counter_persistence_and_increment(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            seq_file = os.path.join(tmpdir, "test_seq.txt")
            sm1 = StorageManager(mount_point=tmpdir, sequence_file=seq_file)
            p1 = sm1.generate_video_path(uptime_s=15.0, throttled_state="throttled=0x0")
            self.assertIn("clip_00001_boot15s_pwrOK.mp4", p1)

            p2 = sm1.generate_video_path(uptime_s=16.0, throttled_state="throttled=0x0")
            self.assertIn("clip_00002_boot16s_pwrOK.mp4", p2)

            # Re-instantiating StorageManager should pick up the persisted sequence
            sm2 = StorageManager(mount_point=tmpdir, sequence_file=seq_file)
            p3 = sm2.generate_video_path(uptime_s=17.0, throttled_state="throttled=0x0")
            self.assertIn("clip_00003_boot17s_pwrOK.mp4", p3)

    def test_sequence_counter_fallback_scan_when_file_missing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            seq_file = os.path.join(tmpdir, "missing_seq.txt")
            rec_dir = os.path.join(tmpdir, StorageManager.DEFAULT_DIR_NAME)
            os.makedirs(rec_dir, exist_ok=True)
            # Create existing clips in directory
            with open(os.path.join(rec_dir, "clip_00007_boot12s_pwrOK.mp4"), "w") as f:
                f.write("test")
            with open(os.path.join(rec_dir, "clip_00012_boot14s_pwrWARN.mp4"), "w") as f:
                f.write("test")

            sm = StorageManager(mount_point=tmpdir, sequence_file=seq_file)
            next_path = sm.generate_video_path(uptime_s=10.0, throttled_state="throttled=0x0")
            # Next should be 13 (max 12 + 1)
            self.assertIn("clip_00013_boot10s_pwrOK.mp4", next_path)

    @patch("os.path.isdir")
    @patch("os.path.exists")
    def test_sd_card_path_resolution_bookworm(self, mock_exists, mock_isdir):
        # On Raspberry Pi OS Bookworm, /boot/firmware is the FAT partition
        mock_exists.side_effect = lambda p: p == "/boot/firmware"
        mock_isdir.side_effect = lambda p: p == "/boot/firmware"
        sm = StorageManager(use_sd_card=True)
        self.assertEqual(sm.recordings_dir, "/boot/firmware/Wild_Life_Recordings")

    @patch("os.path.isdir")
    @patch("os.path.exists")
    def test_sd_card_path_resolution_bullseye(self, mock_exists, mock_isdir):
        # On Raspberry Pi OS Bullseye, /boot is the FAT partition
        mock_exists.side_effect = lambda p: p == "/boot"
        mock_isdir.side_effect = lambda p: p == "/boot"
        sm = StorageManager(use_sd_card=True)
        self.assertEqual(sm.recordings_dir, "/boot/Wild_Life_Recordings")

    @patch("os.makedirs")
    def test_sd_card_mount_creates_directory(self, mock_makedirs):
        sm = StorageManager(use_sd_card=True)
        res = sm.mount()
        self.assertTrue(res)
        mock_makedirs.assert_called_with(sm.recordings_dir, exist_ok=True)

    @patch("subprocess.run")
    @patch("os.sync")
    def test_sd_card_unmount_flushes_sync(self, mock_sync, mock_run):
        sm = StorageManager(use_sd_card=True)
        res = sm.unmount()
        self.assertTrue(res)
        mock_sync.assert_called_once()
        mock_run.assert_called_with(
            ["sync"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False
        )


if __name__ == "__main__":
    unittest.main()

