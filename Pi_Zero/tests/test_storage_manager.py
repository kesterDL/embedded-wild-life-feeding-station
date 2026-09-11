import os
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
        mock_makedirs.assert_called_with("/mnt/usb_storage", exist_ok=True)
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
    def test_generate_video_path_format(self, mock_makedirs):
        path = self.sm.generate_video_path(timestamp="20260910_123000")
        expected_path = "/mnt/usb_storage/videos/clip_20260910_123000.mp4"
        self.assertEqual(path, expected_path)
        mock_makedirs.assert_called_with("/mnt/usb_storage/videos", exist_ok=True)


if __name__ == "__main__":
    unittest.main()
