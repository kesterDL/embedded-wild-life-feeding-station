"""Unit tests for maintenance.py."""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from Pi_Zero.scripts.maintenance import (
    check_maintenance_remote,
    find_local_boot_partitions,
    get_maintenance_status_local,
    main,
    set_maintenance_local,
    set_maintenance_remote,
)


class TestMaintenance(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.boot_dir = self.test_dir.name

    def tearDown(self):
        self.test_dir.cleanup()

    def test_get_maintenance_status_initially_false(self):
        self.assertFalse(get_maintenance_status_local(self.boot_dir))

    def test_set_maintenance_local_enable_and_disable(self):
        # Enable
        success = set_maintenance_local(self.boot_dir, enable=True)
        self.assertTrue(success)
        self.assertTrue(get_maintenance_status_local(self.boot_dir))
        self.assertTrue(os.path.exists(os.path.join(self.boot_dir, "maintenance")))
        self.assertTrue(os.path.exists(os.path.join(self.boot_dir, "no_shutdown")))

        # Disable
        success = set_maintenance_local(self.boot_dir, enable=False)
        self.assertTrue(success)
        self.assertFalse(get_maintenance_status_local(self.boot_dir))
        self.assertFalse(os.path.exists(os.path.join(self.boot_dir, "maintenance")))
        self.assertFalse(os.path.exists(os.path.join(self.boot_dir, "no_shutdown")))

    @patch("os.path.isdir")
    @patch("os.access")
    def test_find_local_boot_partitions(self, mock_access, mock_isdir):
        mock_isdir.side_effect = lambda p: p == "/Volumes/bootfs"
        mock_access.return_value = True

        partitions = find_local_boot_partitions()
        self.assertIn("/Volumes/bootfs", partitions)

    @patch("subprocess.run")
    def test_set_maintenance_remote_enable(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        res = set_maintenance_remote("david@pi-3", enable=True)
        self.assertTrue(res)
        mock_run.assert_called_once()
        self.assertIn("touch", mock_run.call_args[0][0][-1])

    @patch("subprocess.run")
    def test_set_maintenance_remote_disable(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        res = set_maintenance_remote("david@pi-3", enable=False)
        self.assertTrue(res)
        mock_run.assert_called_once()
        self.assertIn("rm -f", mock_run.call_args[0][0][-1])

    @patch("subprocess.run")
    def test_check_maintenance_remote(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        self.assertTrue(check_maintenance_remote("david@pi-3"))

        mock_run.return_value = MagicMock(returncode=1)
        self.assertFalse(check_maintenance_remote("david@pi-3"))

        mock_run.return_value = MagicMock(returncode=255)
        self.assertIsNone(check_maintenance_remote("david@pi-3"))

    @patch("Pi_Zero.scripts.maintenance.find_local_boot_partitions")
    def test_main_local_enable(self, mock_find):
        mock_find.return_value = [self.boot_dir]
        with patch("sys.argv", ["maintenance.py", "on"]):
            code = main()
            self.assertEqual(code, 0)
            self.assertTrue(get_maintenance_status_local(self.boot_dir))

    @patch("Pi_Zero.scripts.maintenance.find_local_boot_partitions")
    def test_main_local_status(self, mock_find):
        mock_find.return_value = [self.boot_dir]
        set_maintenance_local(self.boot_dir, enable=True)
        with patch("sys.argv", ["maintenance.py", "status"]):
            code = main()
            self.assertEqual(code, 0)

    def test_hardware_toggling_in_config_txt(self):
        config_path = os.path.join(self.boot_dir, "config.txt")
        with open(config_path, "w") as f:
            f.write("dtoverlay=disable-bt\n")

        # Field mode: should disable Wi-Fi and HDMI
        set_maintenance_local(self.boot_dir, enable=False, toggle_hardware=True)
        with open(config_path, "r") as f:
            content = f.read()
        self.assertIn("dtoverlay=disable-wifi", content)
        self.assertIn("hdmi_blanking=2", content)

        # Bench mode: should comment out disable-wifi and hdmi_blanking
        set_maintenance_local(self.boot_dir, enable=True, toggle_hardware=True)
        with open(config_path, "r") as f:
            content = f.read()
        self.assertIn("# dtoverlay=disable-wifi", content)
        self.assertIn("# hdmi_blanking=2", content)

    @patch("Pi_Zero.scripts.maintenance.find_local_boot_partitions")
    def test_main_bench_and_field_actions(self, mock_find):
        mock_find.return_value = [self.boot_dir]
        config_path = os.path.join(self.boot_dir, "config.txt")
        with open(config_path, "w") as f:
            f.write("dtoverlay=disable-bt\n")

        # Run field
        with patch("sys.argv", ["maintenance.py", "field"]):
            code = main()
            self.assertEqual(code, 0)
            self.assertFalse(get_maintenance_status_local(self.boot_dir))

        # Run bench
        with patch("sys.argv", ["maintenance.py", "bench"]):
            code = main()
            self.assertEqual(code, 0)
            self.assertTrue(get_maintenance_status_local(self.boot_dir))


if __name__ == "__main__":
    unittest.main()
