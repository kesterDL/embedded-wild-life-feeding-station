import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from Pi_Zero.scripts.test_camera_integration import (
    check_camera_detection,
    package_h264_to_mp4,
    run_integration_test,
    print_troubleshooting_tips,
)
from Pi_Zero.src.camera_service import CameraError


class TestCameraIntegrationScript(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_check_camera_detection_found(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/rpicam-hello"
        mock_run.return_value = MagicMock(
            stdout="Available cameras\n0 : ov5647 [2592x1944] (/base/soc/i2c0mux/i2c@1/ov5647@36)\n",
            stderr="",
            returncode=0
        )
        detected, details = check_camera_detection("rpicam-vid")
        self.assertTrue(detected)
        self.assertIn("ov5647", details)

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_check_camera_detection_none_available(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/rpicam-hello"
        mock_run.return_value = MagicMock(
            stdout="",
            stderr="No cameras available!",
            returncode=1
        )
        detected, details = check_camera_detection("rpicam-vid")
        self.assertFalse(detected)
        self.assertIn("No cameras available", details)

    def test_run_integration_test_dry_run(self):
        output_path = os.path.join(self.temp_dir, "dry_run_test.mp4")
        success = run_integration_test(
            duration_sec=1,
            output_path=output_path,
            dry_run=True
        )
        self.assertTrue(success)
        self.assertTrue(os.path.exists(output_path))
        self.assertGreater(os.path.getsize(output_path), 0)

    @patch("Pi_Zero.scripts.test_camera_integration.package_h264_to_mp4")
    @patch("Pi_Zero.scripts.test_camera_integration.check_camera_detection")
    @patch("shutil.which")
    @patch("Pi_Zero.src.camera_service.CameraService.record_video")
    def test_run_integration_test_success_with_mux(self, mock_record, mock_which, mock_detect, mock_pkg):
        mock_detect.return_value = (True, "Available cameras: ov5647")
        mock_which.side_effect = lambda cmd: "/usr/bin/" + os.path.basename(cmd) if any(x in cmd for x in ["rpicam", "MP4Box"]) else None
        output_path = os.path.join(self.temp_dir, "real_test.mp4")

        def record_side_effect(path):
            with open(path, "wb") as f:
                f.write(b"\x00" * 1024)
            return True

        def pkg_side_effect(h264_p, mp4_p, fps=25):
            with open(mp4_p, "wb") as f:
                f.write(b"\x00" * 2048)
            return True

        mock_record.side_effect = record_side_effect
        mock_pkg.side_effect = pkg_side_effect

        success = run_integration_test(
            duration_sec=20,
            output_path=output_path,
            dry_run=False
        )
        self.assertTrue(success)
        self.assertTrue(os.path.exists(output_path))

    @patch("Pi_Zero.scripts.test_camera_integration.check_camera_detection")
    @patch("shutil.which")
    @patch("Pi_Zero.src.camera_service.CameraService.record_video")
    def test_run_integration_test_success_raw_h264(self, mock_record, mock_which, mock_detect):
        mock_detect.return_value = (True, "Available cameras: ov5647")
        mock_which.side_effect = lambda cmd: "/usr/bin/rpicam-vid" if "rpicam" in cmd else None
        output_path = os.path.join(self.temp_dir, "real_test.h264")

        def record_side_effect(path):
            with open(path, "wb") as f:
                f.write(b"\x00" * 1024)
            return True

        mock_record.side_effect = record_side_effect

        success = run_integration_test(
            duration_sec=20,
            output_path=output_path,
            dry_run=False
        )
        self.assertTrue(success)
        self.assertTrue(os.path.exists(output_path))

    @patch("Pi_Zero.scripts.test_camera_integration.check_camera_detection")
    @patch("shutil.which")
    @patch("Pi_Zero.src.camera_service.CameraService.record_video")
    def test_run_integration_test_camera_error(self, mock_record, mock_which, mock_detect):
        mock_detect.return_value = (True, "Available cameras: ov5647")
        mock_which.side_effect = lambda cmd: "/usr/bin/rpicam-vid" if "rpicam" in cmd else None
        output_path = os.path.join(self.temp_dir, "fail_test.h264")
        mock_record.side_effect = CameraError("Hardware timeout")

        success = run_integration_test(
            duration_sec=20,
            output_path=output_path,
            dry_run=False
        )
        self.assertFalse(success)

    @patch("Pi_Zero.scripts.test_camera_integration.check_camera_detection")
    @patch("shutil.which")
    @patch("Pi_Zero.src.camera_service.CameraService.record_video")
    def test_run_integration_test_zero_byte_file(self, mock_record, mock_which, mock_detect):
        mock_detect.return_value = (True, "Available cameras: ov5647")
        mock_which.side_effect = lambda cmd: "/usr/bin/rpicam-vid" if "rpicam" in cmd else None
        output_path = os.path.join(self.temp_dir, "empty_test.h264")

        def record_side_effect(path):
            with open(path, "wb") as f:
                pass
            return True

        mock_record.side_effect = record_side_effect

        success = run_integration_test(
            duration_sec=20,
            output_path=output_path,
            dry_run=False
        )
        self.assertFalse(success)

    @patch("Pi_Zero.scripts.test_camera_integration.check_camera_detection")
    @patch("shutil.which")
    def test_run_integration_test_check_only(self, mock_which, mock_detect):
        mock_detect.return_value = (True, "Available cameras: ov5647")
        mock_which.side_effect = lambda cmd: "/usr/bin/rpicam-vid" if "rpicam" in cmd else None
        output_path = os.path.join(self.temp_dir, "check_only.mp4")

        success = run_integration_test(
            output_path=output_path,
            dry_run=False,
            check_only=True
        )
        self.assertTrue(success)
        self.assertFalse(os.path.exists(output_path))


if __name__ == "__main__":
    unittest.main()
