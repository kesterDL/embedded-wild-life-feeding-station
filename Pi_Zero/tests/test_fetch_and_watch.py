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
    sync_recordings,
    convert_lingering_raw_streams,
    fetch_from_pi,
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

        # Create temporary file that should be ignored by default
        file_temp = os.path.join(self.temp_dir, "clip_20261002_120000_temp.h264")
        with open(file_temp, "wb") as f:
            f.write(b"temp")

        # Create AppleDouble file that should be ignored
        apple_double = os.path.join(self.temp_dir, "._clip_20261002_120000.mp4")
        with open(apple_double, "wb") as f:
            f.write(b"metadata")

        # Create 0-byte file that should be ignored
        empty_file = os.path.join(self.temp_dir, "clip_20261003_000000.mp4")
        with open(empty_file, "wb") as f:
            pass

        candidates = get_candidate_files([self.temp_dir])
        self.assertEqual(len(candidates), 2)
        # Should be sorted newest first
        self.assertEqual(candidates[0], file_new)
        self.assertEqual(candidates[1], file_old)

    def test_get_candidate_files_with_include_temp(self):
        file_temp = os.path.join(self.temp_dir, "clip_20261009_185847_temp.h264")
        with open(file_temp, "wb") as f:
            f.write(b"raw-stream-content")

        candidates = get_candidate_files([self.temp_dir], include_temp=True)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0], file_temp)

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

    @patch("Pi_Zero.scripts.fetch_and_watch.package_to_smooth_mp4")
    def test_sync_recordings_copies_mp4_and_converts_temp_h264(self, mock_package):
        def _mock_pkg(src, dst, fps):
            with open(dst, "wb") as f:
                f.write(b"packaged")
            return True

        mock_package.side_effect = _mock_pkg

        src_dir = os.path.join(self.temp_dir, "src")
        dest_dir = os.path.join(self.temp_dir, "dest")
        os.makedirs(src_dir)
        os.makedirs(dest_dir)

        # 1. Existing MP4 clip
        clip_mp4 = os.path.join(src_dir, "clip_20261009_185839.mp4")
        with open(clip_mp4, "wb") as f:
            f.write(b"mp4-content")

        # 2. Non-empty temp H.264
        clip_temp = os.path.join(src_dir, "clip_20261009_185847_temp.h264")
        with open(clip_temp, "wb") as f:
            f.write(b"h264-stream")

        # 3. 0-byte aborted temp file (should be skipped)
        clip_empty = os.path.join(src_dir, "clip_20261009_185905_temp.h264")
        with open(clip_empty, "wb") as f:
            pass

        # 4. AppleDouble dot file (should be skipped)
        dot_file = os.path.join(src_dir, "._clip_20261009_185839.mp4")
        with open(dot_file, "wb") as f:
            f.write(b"metadata")

        # 5. Lifecycle metrics log
        log_file = os.path.join(src_dir, "lifecycle.log")
        with open(log_file, "w") as f:
            f.write("timestamp,uptime_s,record_s,mux_s,total_cycle_s,status,video_file,throttled\n")

        synced, converted = sync_recordings(src_dir, dest_dir)
        self.assertEqual(synced, 1)
        self.assertEqual(converted, 1)

        # Verify MP4 was copied to dest
        self.assertTrue(os.path.exists(os.path.join(dest_dir, "clip_20261009_185839.mp4")))
        # Verify temp H.264 was converted to clean MP4 in dest
        self.assertTrue(os.path.exists(os.path.join(dest_dir, "clip_20261009_185847.mp4")))
        # Verify lifecycle.log was copied to dest
        self.assertTrue(os.path.exists(os.path.join(dest_dir, "lifecycle.log")))
        # Verify 0-byte and dot files were not copied
        self.assertFalse(os.path.exists(os.path.join(dest_dir, "clip_20261009_185905.mp4")))
        self.assertFalse(os.path.exists(os.path.join(dest_dir, "._clip_20261009_185839.mp4")))

    @patch("Pi_Zero.scripts.fetch_and_watch.package_to_smooth_mp4")
    def test_convert_lingering_raw_streams(self, mock_package):
        def _mock_pkg(src, dst, fps):
            with open(dst, "wb") as f:
                f.write(b"packaged")
            return True

        mock_package.side_effect = _mock_pkg

        raw_stream = os.path.join(self.temp_dir, "camera_test_20261009_172437.h264")
        with open(raw_stream, "wb") as f:
            f.write(b"raw-data")

        converted = convert_lingering_raw_streams(self.temp_dir)
        self.assertEqual(converted, 1)
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, "camera_test_20261009_172437.mp4")))

    @patch("Pi_Zero.scripts.fetch_and_watch.package_to_smooth_mp4")
    def test_sync_recordings_delete_source(self, mock_package):
        mock_package.return_value = True

        src_dir = os.path.join(self.temp_dir, "src_del")
        dest_dir = os.path.join(self.temp_dir, "dest_del")
        os.makedirs(src_dir)
        os.makedirs(dest_dir)

        clip_mp4 = os.path.join(src_dir, "clip_test.mp4")
        with open(clip_mp4, "wb") as f:
            f.write(b"mp4-content")

        log_file = os.path.join(src_dir, "lifecycle.log")
        with open(log_file, "w") as f:
            f.write("log-data\n")

        # 1. Test with delete_source=True (default)
        sync_recordings(src_dir, dest_dir, delete_source=True)
        # MP4 should be copied to dest and deleted from src
        self.assertTrue(os.path.exists(os.path.join(dest_dir, "clip_test.mp4")))
        self.assertFalse(os.path.exists(clip_mp4))
        # Log should be copied to dest but retained in src
        self.assertTrue(os.path.exists(os.path.join(dest_dir, "lifecycle.log")))
        self.assertTrue(os.path.exists(log_file))

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_fetch_from_pi_rsync_delete_source(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/rsync"
        mock_run.return_value = MagicMock(returncode=0)

        dest_dir = os.path.join(self.temp_dir, "dest_remote")

        # 1. Default delete_source=True
        fetch_from_pi(host="david@pi-3", dest_dir=dest_dir, delete_source=True)
        # Should have run rsync with --remove-source-files, and then ssh rm
        self.assertEqual(mock_run.call_count, 2)
        rsync_cmd = mock_run.call_args_list[0][0][0]
        self.assertIn("--remove-source-files", rsync_cmd)
        ssh_cmd = mock_run.call_args_list[1][0][0]
        self.assertEqual(ssh_cmd[0], "ssh")
        self.assertIn("rm -f", ssh_cmd[4])

        mock_run.reset_mock()

        # 2. delete_source=False
        fetch_from_pi(host="david@pi-3", dest_dir=dest_dir, delete_source=False)
        self.assertEqual(mock_run.call_count, 1)
        rsync_cmd = mock_run.call_args_list[0][0][0]
        self.assertNotIn("--remove-source-files", rsync_cmd)


if __name__ == "__main__":
    unittest.main()
