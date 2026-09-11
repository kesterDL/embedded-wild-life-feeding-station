import unittest
from unittest.mock import patch, MagicMock
from Pi_Zero.src.camera_service import CameraService, CameraError


class TestCameraService(unittest.TestCase):

    def setUp(self):
        self.camera = CameraService(
            width=1920,
            height=1080,
            fps=30,
            duration_ms=20000
        )

    @patch("shutil.which")
    def test_resolve_binary_preference(self, mock_which):
        # Should prefer rpicam-vid over libcamera-vid
        mock_which.side_effect = lambda cmd: (
            "/usr/bin/rpicam-vid" if cmd == "rpicam-vid" else None
        )
        self.assertEqual(self.camera.resolve_binary(), "/usr/bin/rpicam-vid")

    @patch("shutil.which")
    def test_resolve_binary_fallback(self, mock_which):
        # If rpicam-vid is not installed, fall back to libcamera-vid
        mock_which.side_effect = lambda cmd: (
            "/usr/bin/libcamera-vid" if cmd == "libcamera-vid" else None
        )
        self.assertEqual(self.camera.resolve_binary(), "/usr/bin/libcamera-vid")

    def test_build_command_structure(self):
        with patch.object(self.camera, "resolve_binary", return_value="rpicam-vid"):
            cmd = self.camera.build_command("/mnt/usb_storage/videos/clip_test.mp4")
            self.assertEqual(cmd[0], "rpicam-vid")
            self.assertIn("--width", cmd)
            self.assertIn("1920", cmd)
            self.assertIn("--height", cmd)
            self.assertIn("1080", cmd)
            self.assertIn("--framerate", cmd)
            self.assertIn("30", cmd)
            self.assertIn("-t", cmd)
            self.assertIn("20000", cmd)
            self.assertIn("-o", cmd)
            self.assertIn("/mnt/usb_storage/videos/clip_test.mp4", cmd)

    @patch("subprocess.run")
    def test_record_video_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        with patch.object(self.camera, "resolve_binary", return_value="rpicam-vid"):
            result = self.camera.record_video("/mnt/usb_storage/videos/clip_test.mp4")
            self.assertTrue(result)
            mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_record_video_failure_raises_camera_error(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="Camera hardware timeout")
        with patch.object(self.camera, "resolve_binary", return_value="rpicam-vid"):
            with self.assertRaises(CameraError):
                self.camera.record_video("/mnt/usb_storage/videos/clip_test.mp4")


if __name__ == "__main__":
    unittest.main()
