import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from Pi_Zero.scripts.fetch_and_watch import (
    find_mounted_sd_card_dir,
    is_mp4_container,
    get_candidate_files,
    package_to_smooth_mp4,
)


class TestFetchAndWatch(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("os.path.isdir")
    def test_find_mounted_sd_card_dir_boot(self, mock_isdir):
        mock_isdir.side_effect = lambda p: p == "/Volumes/boot/Wild_Life_Recordings"
        sd_dir = find_mounted_sd_card_dir()
        self.assertEqual(sd_dir, "/Volumes/boot/Wild_Life_Recordings")

    @patch("glob.glob")
    @patch("os.path.isdir")
    def test_find_mounted_sd_card_dir_custom_volume(self, mock_isdir, mock_glob):
        mock_isdir.side_effect = lambda p: p == "/Volumes/MySD/Wild_Life_Recordings"
        mock_glob.return_value = ["/Volumes/MySD/Wild_Life_Recordings"]
        sd_dir = find_mounted_sd_card_dir()
        self.assertEqual(sd_dir, "/Volumes/MySD/Wild_Life_Recordings")

    @patch("glob.glob")
    @patch("os.path.isdir")
    def test_find_mounted_sd_card_dir_none(self, mock_isdir, mock_glob):
        mock_isdir.return_value = False
        mock_glob.return_value = []
        sd_dir = find_mounted_sd_card_dir()
        self.assertIsNone(sd_dir)

    def test_is_mp4_container_valid(self):
        mp4_path = os.path.join(self.temp_dir, "valid.mp4")
        with open(mp4_path, "wb") as f:
            f.write(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 32)
        self.assertTrue(is_mp4_container(mp4_path))

    def test_is_mp4_container_invalid(self):
        h264_path = os.path.join(self.temp_dir, "raw.h264")
        with open(h264_path, "wb") as f:
            f.write(b"\x00\x00\x00\x01" + b"\x67\x42" * 16)
        self.assertFalse(is_mp4_container(h264_path))

    def test_get_candidate_files_filtering_and_sorting(self):
        # Create older mp4
        file_old = os.path.join(self.temp_dir, "clip_20261001_100000.mp4")
        with open(file_old, "wb") as f:
            f.write(b"data")
        os.utime(file_old, (1000, 1000))

        # Create newer h264
        file_new = os.path.join(self.temp_dir, "clip_20261002_120000.h264")
        with open(file_new, "wb") as f:
            f.write(b"data")
        os.utime(file_new, (2000, 2000))

        # Create temporary file that should be ignored
        file_temp = os.path.join(self.temp_dir, "clip_20261002_120000_temp.h264")
        with open(file_temp, "wb") as f:
            f.write(b"temp")

        candidates = get_candidate_files([self.temp_dir])
        self.assertEqual(len(candidates), 2)
        # Should be sorted newest first
        self.assertEqual(candidates[0], file_new)
        self.assertEqual(candidates[1], file_old)

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_package_to_smooth_mp4_ffmpeg(self, mock_run, mock_which):
        mock_which.return_value = "/usr/local/bin/ffmpeg"
        mock_run.return_value = MagicMock(returncode=0)

        in_file = os.path.join(self.temp_dir, "input.h264")
        out_file = os.path.join(self.temp_dir, "output.mp4")
        with open(in_file, "wb") as f:
            f.write(b"raw")
        with open(out_file, "wb") as f:
            f.write(b"mp4")

        success = package_to_smooth_mp4(in_file, out_file, fps=25)
        self.assertTrue(success)
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        self.assertIn("-r", cmd)
        self.assertIn("25", cmd)
        self.assertIn(out_file, cmd)


if __name__ == "__main__":
    unittest.main()
