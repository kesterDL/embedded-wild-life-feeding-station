import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from Pi_Zero.scripts.visualize_metrics import (
    compute_kpis,
    decode_throttled_bitmask,
    generate_html_dashboard,
    main,
    parse_lifecycle_log,
)


class TestVisualizeMetrics(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_path = os.path.join(self.temp_dir.name, "lifecycle.log")
        self.recordings_dir = os.path.join(self.temp_dir.name, "recordings")
        os.makedirs(self.recordings_dir, exist_ok=True)

        # Sample CSV log content
        self.sample_csv = (
            "timestamp,uptime_s,record_s,mux_s,total_cycle_s,status,video_file,throttled\n"
            "2026-10-15 14:09:20,11.70,21.80,4.20,26.00,SUCCESS,clip_00001_boot12s_pwrOK.mp4,throttled=0x0\n"
            "2026-10-15 15:24:28,17.80,22.00,5.80,27.80,SUCCESS,clip_00002_boot18s_pwrWARN.mp4,throttled=0x50005\n"
            "2026-10-15 15:25:17,18.10,21.90,0.00,21.90,CAMERA_ERROR,clip_00003_boot18s_pwrWARN.mp4,throttled=0x50005\n"
            "2026-10-15 16:00:00,1050.00,20.00,1.50,21.50,SUCCESS,clip_00004_boot1050s_pwrOK.mp4,throttled=0x0\n"
        )
        with open(self.log_path, "w", encoding="utf-8") as f:
            f.write(self.sample_csv)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_decode_throttled_bitmask_clean(self):
        result = decode_throttled_bitmask("throttled=0x0")
        self.assertFalse(result["is_throttled"])
        self.assertFalse(result["active_undervoltage"])
        self.assertFalse(result["active_throttling"])
        self.assertEqual(result["badge"], "pwrOK")
        self.assertIn("Clean", result["description"])

    def test_decode_throttled_bitmask_brownout(self):
        result = decode_throttled_bitmask("throttled=0x50005")
        self.assertTrue(result["is_throttled"])
        self.assertTrue(result["active_undervoltage"])
        self.assertTrue(result["active_throttling"])
        self.assertTrue(result["past_undervoltage"])
        self.assertTrue(result["past_throttling"])
        self.assertEqual(result["badge"], "pwrWARN")
        self.assertIn("Under-voltage", result["description"])

    def test_decode_throttled_bitmask_none_or_unknown(self):
        res_none = decode_throttled_bitmask(None)
        self.assertEqual(res_none["badge"], "pwrOK")
        self.assertFalse(res_none["is_throttled"])

        res_na = decode_throttled_bitmask("N/A")
        self.assertEqual(res_na["badge"], "pwrOK")
        self.assertFalse(res_na["is_throttled"])

    def test_parse_lifecycle_log_valid(self):
        records = parse_lifecycle_log(self.log_path)
        self.assertEqual(len(records), 4)

        first = records[0]
        self.assertEqual(first["timestamp"], "2026-10-15 14:09:20")
        self.assertEqual(first["uptime_s"], 11.70)
        self.assertEqual(first["record_s"], 21.80)
        self.assertEqual(first["mux_s"], 4.20)
        self.assertEqual(first["total_cycle_s"], 26.00)
        self.assertEqual(first["status"], "SUCCESS")
        self.assertEqual(first["video_file"], "clip_00001_boot12s_pwrOK.mp4")
        self.assertEqual(first["throttled"], "throttled=0x0")
        self.assertFalse(first["is_throttled"])
        self.assertEqual(first["badge"], "pwrOK")

    def test_parse_lifecycle_log_missing_file(self):
        records = parse_lifecycle_log("/non/existent/path/lifecycle.log")
        self.assertEqual(records, [])

    def test_parse_lifecycle_log_handles_na_and_malformed(self):
        bad_csv = (
            "timestamp,uptime_s,record_s,mux_s,total_cycle_s,status,video_file,throttled\n"
            "2026-10-15 10:00:00,N/A,invalid,,N/A,STORAGE_ERROR,none,UNKNOWN\n"
        )
        bad_log = os.path.join(self.temp_dir.name, "bad.log")
        with open(bad_log, "w", encoding="utf-8") as f:
            f.write(bad_csv)

        records = parse_lifecycle_log(bad_log)
        self.assertEqual(len(records), 1)
        self.assertIsNone(records[0]["uptime_s"])
        self.assertEqual(records[0]["status"], "STORAGE_ERROR")

    def test_compute_kpis(self):
        records = parse_lifecycle_log(self.log_path)
        # Note: 4th record has uptime 1050s, which is a maintenance run (>600s)
        kpis = compute_kpis(records)

        self.assertEqual(kpis["total_cycles"], 4)
        self.assertEqual(kpis["cold_boot_cycles"], 3)  # Excludes uptime > 600s
        self.assertEqual(kpis["success_count"], 3)
        self.assertEqual(kpis["camera_error_count"], 1)
        self.assertEqual(kpis["storage_error_count"], 0)
        self.assertAlmostEqual(kpis["success_rate_pct"], 75.0, places=1)

        # Clean vs Brownout on cold boot cycles
        self.assertEqual(kpis["clean_power_count"], 1)
        self.assertEqual(kpis["brownout_count"], 2)
        self.assertAlmostEqual(kpis["brownout_rate_pct"], 66.7, places=1)
        self.assertAlmostEqual(kpis["avg_uptime_clean_s"], 11.70, places=2)
        self.assertAlmostEqual(kpis["avg_uptime_brownout_s"], (17.80 + 18.10) / 2, places=2)

    def test_generate_html_dashboard_creates_file_and_contains_panels(self):
        records = parse_lifecycle_log(self.log_path)
        output_html = os.path.join(self.temp_dir.name, "dashboard.html")

        # Create a dummy video file in recordings_dir to test payload calculation
        dummy_clip = os.path.join(self.recordings_dir, "clip_00001_boot12s_pwrOK.mp4")
        with open(dummy_clip, "wb") as f:
            f.write(b"0" * 1024 * 1024 * 5)  # 5 MB

        generate_html_dashboard(records, self.recordings_dir, output_html)

        self.assertTrue(os.path.exists(output_html))
        with open(output_html, "r", encoding="utf-8") as f:
            html = f.read()

        # Check for self-contained structure
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("Squirrel Feeder — Metrics & Diagnostics Dashboard", html)

        # Check for 5 visual panel IDs
        self.assertIn('id="startupChart"', html)
        self.assertIn('id="phaseChart"', html)
        self.assertIn('id="reliabilityChart"', html)
        self.assertIn('id="payloadChart"', html)
        self.assertIn('id="metricsTable"', html)

        # Check KPI cards
        self.assertIn("Total Capture Cycles", html)
        self.assertIn("Success Rate", html)
        self.assertIn("Brownout Rate", html)

        # Check embedded Chart.js library presence
        self.assertTrue("Chart" in html or "chart.umd.min.js" in html)

    @patch("webbrowser.open")
    def test_main_cli(self, mock_webbrowser):
        output_html = os.path.join(self.temp_dir.name, "cli_dashboard.html")
        args = [
            "--log", self.log_path,
            "--recordings-dir", self.recordings_dir,
            "--output", output_html,
            "--no-open"
        ]
        ret = main(args)
        self.assertEqual(ret, 0)
        self.assertTrue(os.path.exists(output_html))
        mock_webbrowser.assert_not_called()

    @patch("webbrowser.open")
    def test_main_cli_with_open(self, mock_webbrowser):
        output_html = os.path.join(self.temp_dir.name, "cli_open.html")
        args = [
            "--log", self.log_path,
            "--recordings-dir", self.recordings_dir,
            "--output", output_html,
            "--open"
        ]
        ret = main(args)
        self.assertEqual(ret, 0)
        self.assertTrue(os.path.exists(output_html))
        mock_webbrowser.assert_called_once()


if __name__ == "__main__":
    unittest.main()
