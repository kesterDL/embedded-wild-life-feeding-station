import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from Pi_Zero.src.orchestrator import MediaOrchestrator
from Pi_Zero.src.storage_manager import StorageNotFoundError
from Pi_Zero.src.camera_service import CameraError


class TestMediaOrchestrator(unittest.TestCase):

    def setUp(self):
        self.mock_storage = MagicMock()
        self.mock_camera = MagicMock()
        self.mock_camera.last_record_duration = 20.0
        self.mock_camera.last_mux_duration = 5.2
        self.mock_bridge = MagicMock()

        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_path = os.path.join(self.temp_dir.name, "lifecycle.log")

        self.orchestrator = MediaOrchestrator(
            storage_manager=self.mock_storage,
            camera_service=self.mock_camera,
            watchdog_bridge=self.mock_bridge,
            log_path=self.log_path
        )
        self.maintenance_patcher = patch.object(self.orchestrator, "is_maintenance_mode", return_value=False)
        self.maintenance_patcher.start()

    def tearDown(self):
        self.maintenance_patcher.stop()
        self.temp_dir.cleanup()

    @patch("Pi_Zero.src.orchestrator.get_throttled_state", return_value="throttled=0x0")
    @patch("Pi_Zero.src.orchestrator.get_system_uptime", return_value=16.48)
    def test_full_lifecycle_success(self, mock_uptime, mock_throttled):
        self.mock_storage.generate_video_path.return_value = "/mnt/usb_storage/videos/clip_00001_boot16s_pwrOK.mp4"
        with patch.object(self.orchestrator, "halt_system") as mock_halt:
            result = self.orchestrator.run_cycle(dry_run=False)
            self.assertTrue(result)
            self.mock_storage.mount.assert_called_once()
            self.mock_storage.generate_video_path.assert_called_once_with(
                uptime_s=16.48, throttled_state="throttled=0x0"
            )
            self.mock_camera.record_video.assert_called_with("/mnt/usb_storage/videos/clip_00001_boot16s_pwrOK.mp4")
            self.mock_storage.unmount.assert_called_once()
            self.mock_bridge.signal_shutdown_ack.assert_called_once()
            mock_halt.assert_called_once()

        self.assertTrue(os.path.exists(self.log_path))
        with open(self.log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("timestamp,uptime_s,record_s,mux_s,total_cycle_s,status,video_file,throttled", lines[0])
        self.assertIn("SUCCESS", lines[1])
        self.assertIn("clip_00001_boot16s_pwrOK.mp4", lines[1])
        self.assertIn("20.00", lines[1])
        self.assertIn("5.20", lines[1])

    def test_missing_storage_aborts_immediately(self):
        self.mock_storage.mount.side_effect = StorageNotFoundError("No USB device")
        with patch.object(self.orchestrator, "halt_system") as mock_halt:
            result = self.orchestrator.run_cycle(dry_run=False)
            self.assertFalse(result)
            # Camera recording must NOT be executed if storage is missing
            self.mock_camera.record_video.assert_not_called()
            # Must signal ACK and halt to save battery
            self.mock_bridge.signal_shutdown_ack.assert_called_once()
            mock_halt.assert_called_once()

        self.assertTrue(os.path.exists(self.log_path))
        with open(self.log_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("STORAGE_ERROR", content)
        self.assertIn("none", content)

    def test_camera_error_cleans_up_and_halts(self):
        self.mock_storage.generate_video_path.return_value = "/mnt/usb_storage/videos/clip_err.mp4"
        self.mock_camera.record_video.side_effect = CameraError("Hardware fault")
        with patch.object(self.orchestrator, "halt_system") as mock_halt:
            result = self.orchestrator.run_cycle(dry_run=False)
            self.assertFalse(result)
            # Storage must still be unmounted
            self.mock_storage.unmount.assert_called_once()
            # ACK signaled and halt executed
            self.mock_bridge.signal_shutdown_ack.assert_called_once()
            mock_halt.assert_called_once()

        self.assertTrue(os.path.exists(self.log_path))
        with open(self.log_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("CAMERA_ERROR", content)
        self.assertIn("clip_err.mp4", content)

    def test_maintenance_mode_skips_shutdown_ack_and_halt(self):
        self.mock_storage.generate_video_path.return_value = "/mnt/usb_storage/videos/clip_maint.mp4"
        self.maintenance_patcher.stop()
        with patch.object(self.orchestrator, "is_maintenance_mode", return_value=True), \
             patch.object(self.orchestrator, "halt_system") as mock_halt:
            result = self.orchestrator.run_cycle(dry_run=False)
            self.assertTrue(result)
            self.mock_storage.unmount.assert_called_once()
            # Arduino Nano ACK and OS halt MUST NOT be called in maintenance mode
            self.mock_bridge.signal_shutdown_ack.assert_not_called()
            mock_halt.assert_not_called()
        self.maintenance_patcher.start()

    def test_dry_run_skips_shutdown_ack_and_halt(self):
        self.mock_storage.generate_video_path.return_value = "/mnt/usb_storage/videos/clip_dry.mp4"
        with patch.object(self.orchestrator, "halt_system") as mock_halt:
            result = self.orchestrator.run_cycle(dry_run=True)
            self.assertTrue(result)
            self.mock_storage.unmount.assert_called_once()
            # Arduino Nano ACK and OS halt MUST NOT be called in dry-run mode
            self.mock_bridge.signal_shutdown_ack.assert_not_called()
            mock_halt.assert_not_called()

    def test_storage_error_in_maintenance_mode_skips_shutdown_ack_and_halt(self):
        self.mock_storage.mount.side_effect = StorageNotFoundError("No USB device")
        self.maintenance_patcher.stop()
        with patch.object(self.orchestrator, "is_maintenance_mode", return_value=True), \
             patch.object(self.orchestrator, "halt_system") as mock_halt:
            result = self.orchestrator.run_cycle(dry_run=False)
            self.assertFalse(result)
            self.mock_bridge.signal_shutdown_ack.assert_not_called()
            mock_halt.assert_not_called()
        self.maintenance_patcher.start()


if __name__ == "__main__":
    unittest.main()

