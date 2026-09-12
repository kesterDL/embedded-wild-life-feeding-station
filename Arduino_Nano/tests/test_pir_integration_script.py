import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Ensure Arduino_Nano directory is in sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from Arduino_Nano.integ_test_scripts.test_pir_integration import (
    MockArduinoSerial,
    PIRIntegrationTester,
    list_candidate_serial_ports,
    main,
    print_pir_troubleshooting,
)


class TestPIRIntegrationScript(unittest.TestCase):
    """Unit tests for PIR hardware integration test script."""

    def test_mock_arduino_serial_handshake(self):
        ser = MockArduinoSerial()
        ser.write(b"PING\n")
        response = ser.readline().decode("utf-8")
        # Drain init message
        if "[INIT]" in response:
            response = ser.readline().decode("utf-8")
        if "[WARMUP]" in response:
            response = ser.readline().decode("utf-8")
        self.assertIn("[PONG]", response)

    def test_mock_arduino_serial_skip_warmup(self):
        ser = MockArduinoSerial()
        ser.write(b"SKIP\n")
        messages = []
        for _ in range(5):
            line = ser.readline().decode("utf-8")
            messages.append(line)
        joined = "".join(messages)
        self.assertTrue("[WARMUP_SKIPPED]" in joined or "[READY]" in joined)

    def test_list_candidate_serial_ports(self):
        with patch("glob.glob") as mock_glob:
            mock_glob.side_effect = lambda pat: ["/dev/cu.usbserial-1410"] if "usbserial" in pat else []
            ports = list_candidate_serial_ports()
            self.assertIn("/dev/cu.usbserial-1410", ports)

    def test_pir_tester_dry_run_full_cycle(self):
        tester = PIRIntegrationTester(dry_run=True, skip_warmup=True)
        connected = tester.connect()
        self.assertTrue(connected)

        # Handshake
        handshake_ok = tester.run_handshake_check()
        self.assertTrue(handshake_ok)
        self.assertIn("Handshake", tester.results)
        self.assertTrue(tester.results["Handshake"][0])

        # Warmup
        warmup_ok = tester.handle_warmup_phase()
        self.assertTrue(warmup_ok)

        # Quiescent noise test
        quiescent_ok = tester.run_quiescent_noise_test()
        self.assertTrue(quiescent_ok)
        self.assertIn("Quiescent Test", tester.results)
        self.assertTrue(tester.results["Quiescent Test"][0])

        # Active motion test
        motion_ok = tester.run_active_motion_test()
        self.assertTrue(motion_ok)
        self.assertIn("Interrupt INT0", tester.results)
        self.assertTrue(tester.results["Interrupt INT0"][0])
        self.assertTrue(tester.results["Pin D2 HIGH"][0])

        # Cooldown test
        cooldown_ok = tester.run_cooldown_reset_test()
        self.assertTrue(cooldown_ok)
        self.assertIn("Sensor Reset (LOW)", tester.results)
        self.assertTrue(tester.results["Sensor Reset (LOW)"][0])

        # Summary
        all_passed = tester.print_summary_report()
        self.assertTrue(all_passed)
        tester.close()

    def test_pir_tester_quiescent_failure_detection(self):
        tester = PIRIntegrationTester(dry_run=True, skip_warmup=True)
        tester.connect()
        # Inject false trigger in response queue
        tester.ser._response_queue.append("[TRIGGER] False motion detected on D2!")
        quiescent_ok = tester.run_quiescent_noise_test()
        self.assertFalse(quiescent_ok)
        self.assertFalse(tester.results["Quiescent Test"][0])
        tester.close()

    def test_main_dry_run_cli(self):
        with patch("sys.argv", ["test_pir_integration.py", "--dry-run", "--skip-warmup"]):
            exit_code = main()
            self.assertEqual(exit_code, 0)

    def test_troubleshoot_cli(self):
        with patch("sys.argv", ["test_pir_integration.py", "--troubleshoot"]):
            exit_code = main()
            self.assertEqual(exit_code, 0)

    def test_dump_sketch_cli(self):
        with patch("sys.argv", ["test_pir_integration.py", "--dump-sketch"]):
            exit_code = main()
            self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
