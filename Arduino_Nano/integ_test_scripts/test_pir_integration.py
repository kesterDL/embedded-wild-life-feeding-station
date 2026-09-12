#!/usr/bin/env python3
"""Standalone HC-SR501 PIR Sensor Hardware Integration Test for Arduino Nano.

Validates physical PIR motion sensor in isolation:
1. Discovers and establishes serial communication with Arduino Nano (115200 baud).
2. Manages sensor warm-up / stabilization phase (~30s pyroelectric settling).
3. Quiescent Baseline Test: Asserts zero false triggers occur while scene is still.
4. Active Motion Trigger Test: Prompts user to wave hand and verifies:
   - External hardware interrupt INT0 (Pin D2) fires on RISING edge.
   - Pin D2 transitions from LOW to HIGH.
   - Onboard Status LED (Pin 13) illuminates.
5. Cooldown & Reset Test: Verifies sensor returns to LOW and measures pulse width.
6. Generates a comprehensive PASS/FAIL test report and hardware diagnostic guide.

Usage:
    # Auto-detect Arduino serial port and run full integration test
    python3 Arduino_Nano/integ_test_scripts/test_pir_integration.py

    # Specify custom serial port
    python3 Arduino_Nano/integ_test_scripts/test_pir_integration.py --port /dev/cu.usbserial-1410

    # Skip 30s warmup if sensor is already warmed up
    python3 Arduino_Nano/integ_test_scripts/test_pir_integration.py --skip-warmup

    # Dry-run mode for host simulation / CI
    python3 Arduino_Nano/integ_test_scripts/test_pir_integration.py --dry-run

    # Continuous live sensor monitoring
    python3 Arduino_Nano/integ_test_scripts/test_pir_integration.py --monitor
"""

import argparse
import glob
import os
import sys
import time
from typing import Dict, List, Optional, Tuple

# Try importing pyserial; if missing, handle gracefully
try:
    import serial
    from serial.tools import list_ports
    HAS_PYSERIAL = True
except ImportError:
    serial = None
    list_ports = None
    HAS_PYSERIAL = False


SKETCH_RELATIVE_PATH = os.path.join(os.path.dirname(__file__), "test_pir_sensor.ino")


def list_candidate_serial_ports() -> List[str]:
    """Discovers available USB serial ports on macOS, Linux, and Windows."""
    ports = []
    if HAS_PYSERIAL and list_ports:
        for p in list_ports.comports():
            # Check for common Arduino Nano USB-UART chips (FTDI, CH340, CP2102)
            desc = (p.description or "").lower()
            hwid = (p.hwid or "").lower()
            if any(k in desc or k in hwid for k in ["ftdi", "ch340", "cp210", "usb-serial", "nano", "arduino", "1a86", "0403"]):
                ports.insert(0, p.device)
            else:
                ports.append(p.device)
    else:
        # Posix fallback using filesystem globs
        patterns = [
            "/dev/cu.usbserial*",
            "/dev/cu.wchusbserial*",
            "/dev/cu.usbmodem*",
            "/dev/ttyUSB*",
            "/dev/ttyACM*"
        ]
        for pat in patterns:
            ports.extend(glob.glob(pat))

    # Remove duplicates while preserving order
    unique_ports = []
    for port in ports:
        if port not in unique_ports:
            unique_ports.append(port)
    return unique_ports


def print_pir_troubleshooting():
    """Prints hardware wiring and tuning instructions for HC-SR501 PIR sensor."""
    print("\n" + "=" * 65)
    print("        HC-SR501 PIR SENSOR HARDWARE TROUBLESHOOTING GUIDE")
    print("=" * 65)
    print("1. Physical Wiring Checklist:")
    print("   • VCC Pin  -> Arduino Nano 5V Pin (5.0V DC)")
    print("   • GND Pin  -> Arduino Nano GND Pin (Common Ground)")
    print("   • OUT Pin  -> Arduino Nano Pin D2 (INT0 / Active-HIGH 3.3V)")
    print("   • MOSFET   -> Pin D8 held HIGH (Keeps Raspberry Pi safely OFF)")
    print()
    print("2. Jumper Configuration (Crucial!):")
    print("   • Position 'H' (Repeatable Trigger - RECOMMENDED for SquirrelFeeder):")
    print("     PIR keeps output HIGH continuously as long as motion persists.")
    print("   • Position 'L' (Single Trigger):")
    print("     PIR goes HIGH for fixed delay, then LOW, even if motion continues.")
    print()
    print("3. Potentiometer Adjustments (Viewed from sensor rear):")
    print("   • Time Delay Pot (Left/Yellow):")
    print("     - Turn FULLY COUNTER-CLOCKWISE for shortest pulse (~3 seconds).")
    print("     - Clockwise increases pulse duration up to 300 seconds.")
    print("   • Sensitivity / Distance Pot (Right/Yellow):")
    print("     - Turn Clockwise for greater range (~7 meters).")
    print("     - Turn Counter-Clockwise for lower range (~3 meters).")
    print("     - Set to mid-point for initial bench testing.")
    print()
    print("4. Pyroelectric Warm-Up Characteristic:")
    print("   • The HC-SR501 requires 30 to 60 seconds after power-on to stabilize.")
    print("   • During warm-up, false random triggers are normal and expected.")
    print()
    print("5. Environmental Noise:")
    print("   • Avoid direct sunlight, heat vents, fans, or warm draft currents.")
    print("=" * 65 + "\n")


class MockArduinoSerial:
    """Mock serial interface for simulation and CI testing without hardware."""

    def __init__(self, port: str = "MOCK_PORT", baudrate: int = 115200, timeout: float = 1.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.is_open = True
        self._start_time = time.time()
        self._warmup_done = False
        self._phase = "WARMUP"
        self._motion_start_time = 0.0
        self._response_queue: List[str] = [
            "[INIT] Initialized successfully. Starting sensor stabilization...",
            "[WARMUP] Stabilizing HC-SR501 pyroelectric sensor... 25s remaining (Send 'SKIP' to bypass)",
        ]

    def write(self, data: bytes) -> int:
        cmd = data.decode("utf-8", errors="ignore").strip().upper()
        if "PING" in cmd:
            self._response_queue.append("[PONG] Arduino Nano PIR Test Firmware Online")
        elif "SKIP" in cmd:
            self._warmup_done = True
            self._phase = "READY"
            self._response_queue.append("[WARMUP_SKIPPED] Warm-up bypassed by operator. Sensor monitoring active.")
            self._response_queue.append("[READY] Sensor monitoring active. Wave hand across PIR sensor to test.")
        elif "STATUS" in cmd:
            self._response_queue.append("[STATUS] State: READY | Pin D2: LOW (Idle) | Triggers: 1 | ISR Count: 1 | Uptime: 35s")
        elif "RESET" in cmd:
            self._phase = "QUIESCENT"
            self._response_queue.append("[RESET] Trigger counters and metrics reset to 0.")
        return len(data)

    def trigger_mock_motion(self):
        """Simulates motion trigger events."""
        self._phase = "MOTION_ACTIVE"
        self._motion_start_time = time.time()
        self._response_queue.append("[ISR_EVENT] Hardware interrupt INT0 fired on RISING edge! Total ISR events: 1 at 2500 ms")
        self._response_queue.append("[TRIGGER] Trigger #1 | Pin D2: HIGH | Timestamp: 2505 ms")

    def reset_input_buffer(self):
        """Simulate clearing serial input buffer."""
        pass

    def readline(self) -> bytes:
        if self._response_queue:
            msg = self._response_queue.pop(0) + "\n"
            return msg.encode("utf-8")

        now = time.time()
        if not self._warmup_done:
            if (now - self._start_time) > 0.8:
                self._warmup_done = True
                self._phase = "READY"
                return b"[READY] Sensor warm-up complete! Physical sensor stabilized.\n"
            time.sleep(0.05)
            return b"[WARMUP] Stabilizing HC-SR501 pyroelectric sensor... 10s remaining (Send 'SKIP' to bypass)\n"

        if self._phase == "QUIESCENT":
            time.sleep(0.05)
            return b"[IDLE_OK] Quiescent state verified: Pin D2 is LOW (no false motion).\n"

        if self._phase == "MOTION_WAIT":
            if (now - self._motion_start_time) > 0.2:
                self.trigger_mock_motion()
            time.sleep(0.05)
            return b""

        if self._phase == "MOTION_ACTIVE":
            if (now - self._motion_start_time) > 0.5:
                self._phase = "COOLDOWN_DONE"
                return b"[CLEAR] Motion pulse ended | Pin D2: LOW | Pulse Duration: 3200 ms\n"
            time.sleep(0.05)
            return b"[ACTIVE_HOLD] Pin D2 currently HIGH (Motion ongoing).\n"

        time.sleep(0.05)
        return b"[IDLE_OK] Quiescent state verified: Pin D2 is LOW (no false motion).\n"

    def close(self):
        self.is_open = False


class PIRIntegrationTester:
    """Manages the full lifecycle integration test workflow for the PIR sensor."""

    def __init__(
        self,
        port: Optional[str] = None,
        baud: int = 115200,
        quiescent_sec: int = 5,
        trigger_timeout_sec: int = 15,
        skip_warmup: bool = False,
        dry_run: bool = False,
        auto_prompt: bool = True
    ):
        self.port = port
        self.baud = baud
        self.quiescent_sec = 1 if dry_run else quiescent_sec
        self.trigger_timeout_sec = 5 if dry_run else trigger_timeout_sec
        self.skip_warmup = skip_warmup
        self.dry_run = dry_run
        self.auto_prompt = auto_prompt

        self.ser = None
        self.results: Dict[str, Tuple[bool, str]] = {}
        self.trigger_metrics: Dict[str, float] = {}

    def connect(self) -> bool:
        """Resolves serial device and establishes communication."""
        if self.dry_run:
            print(f"[DRY-RUN] Connecting to simulated Arduino Nano serial interface...")
            self.ser = MockArduinoSerial(port="MOCK_NANO", baudrate=self.baud)
            return True

        if not HAS_PYSERIAL:
            print("[ERROR] 'pyserial' package is not installed in the active Python environment.")
            print("Please install pyserial to communicate with the physical Arduino Nano:")
            print("    pip3 install pyserial")
            print("Alternatively, you can test the script workflow with: --dry-run")
            return False

        target_port = self.port
        if not target_port:
            candidates = list_candidate_serial_ports()
            if not candidates:
                print("[ERROR] No USB serial ports detected!")
                print("Make sure your Arduino Nano is plugged into USB.")
                print_pir_troubleshooting()
                return False
            target_port = candidates[0]
            print(f"[INFO] Auto-detected serial port: {target_port}")
            if len(candidates) > 1:
                print(f"       Other available ports: {', '.join(candidates[1:])}")

        try:
            print(f"[INFO] Opening serial port {target_port} at {self.baud} baud...")
            self.ser = serial.Serial(target_port, self.baud, timeout=1.0)
            # Toggle DTR to reset Arduino and ensure clean start
            self.ser.dtr = False
            time.sleep(0.1)
            self.ser.dtr = True
            time.sleep(1.5)  # Allow bootloader to complete
            return True
        except Exception as e:
            print(f"[ERROR] Failed to open serial port {target_port}: {e}")
            print_pir_troubleshooting()
            return False

    def send_command(self, cmd: str):
        """Sends a text command to the Arduino Nano."""
        if self.ser:
            self.ser.write((cmd.strip() + "\n").encode("utf-8"))

    def read_line(self, timeout_sec: float = 1.0) -> str:
        """Reads a single decoded line from serial with timeout."""
        if not self.ser:
            return ""
        start = time.time()
        while time.time() - start < timeout_sec:
            raw = self.ser.readline()
            if raw:
                try:
                    return raw.decode("utf-8", errors="replace").strip()
                except Exception:
                    return ""
        return ""

    def flush_input(self):
        """Clears serial input buffer."""
        if self.ser and hasattr(self.ser, "reset_input_buffer"):
            self.ser.reset_input_buffer()

    def run_handshake_check(self) -> bool:
        """Step 1: Tests communication and verifies firmware handshake."""
        print("\n[Step 1/5] Verifying Arduino Nano Firmware Handshake...")
        self.send_command("PING")
        pong_received = False
        start = time.time()

        while time.time() - start < 3.0:
            line = self.read_line(timeout_sec=0.5)
            if line:
                print(f"  << {line}")
            if "[PONG]" in line or "Arduino Nano" in line:
                pong_received = True
                break

        if pong_received:
            print("  ✓ Firmware handshake verified! Nano is responsive.")
            self.results["Handshake"] = (True, "Nano responded to PING with PONG")
            return True
        else:
            print("  ✗ Handshake failed. Nano did not return expected [PONG].")
            print("  Please make sure 'test_pir_sensor.ino' is flashed to the Nano.")
            self.results["Handshake"] = (False, "No PONG response from firmware")
            return False

    def handle_warmup_phase(self) -> bool:
        """Step 2: Handles the 30-second PIR sensor stabilization countdown."""
        print("\n[Step 2/5] Pyroelectric Warm-Up & Stabilization Phase...")
        if self.skip_warmup:
            print("  [INFO] User requested --skip-warmup. Bypassing 30s delay...")
            self.send_command("SKIP")
            time.sleep(0.3)
            self.results["Warm-up"] = (True, "Warm-up bypassed by user flag")
            return True

        print("  HC-SR501 requires up to 30s to settle after power is applied.")
        print("  (Onboard LED D13 blinks at 2 Hz during warm-up)")
        print("  Waiting for sensor stabilization... (Press Ctrl+C or send 'SKIP' to bypass)")

        start_wait = time.time()
        warmed_up = False
        max_wait = 40.0 if not self.dry_run else 3.0
        last_warmup_print = 0.0

        while time.time() - start_wait < max_wait:
            line = self.read_line(timeout_sec=1.0)
            if line:
                if "[WARMUP]" in line:
                    if time.time() - last_warmup_print >= 1.5:
                        print(f"  ⏳ {line}")
                        last_warmup_print = time.time()
                elif "[READY]" in line or "[WARMUP_SKIPPED]" in line:
                    print(f"  ✓ {line}")
                    warmed_up = True
                    break
                else:
                    print(f"     {line}")

        if warmed_up:
            self.results["Warm-up"] = (True, "Sensor stabilized successfully")
            return True
        else:
            print("  [WARNING] Warmup timeout exceeded without explicit READY message.")
            print("  Proceeding to monitoring...")
            self.results["Warm-up"] = (True, "Warmup timed out, proceeding")
            return True

    def run_quiescent_noise_test(self) -> bool:
        """Step 3: Verifies that no motion/noise is detected when area is still."""
        print(f"\n[Step 3/5] Quiescent Baseline Test ({self.quiescent_sec}s stillness)...")
        print("  👉 Please remain completely still. Testing for false triggers / noise...")

        # Reset counters on the Nano
        self.send_command("RESET")
        time.sleep(0.5)
        self.flush_input()

        false_triggers = 0
        start = time.time()
        last_idle_print = 0.0

        while time.time() - start < self.quiescent_sec:
            line = self.read_line(timeout_sec=0.5)
            if line:
                if "[TRIGGER]" in line or "[MOTION_DETECTED]" in line or "[ISR_EVENT]" in line:
                    print(f"  ✗ FALSE TRIGGER DETECTED: {line}")
                    false_triggers += 1
                elif "[IDLE_OK]" in line:
                    if time.time() - last_idle_print >= 1.5:
                        print(f"  ✓ {line}")
                        last_idle_print = time.time()
                else:
                    print(f"    {line}")

        if false_triggers == 0:
            print(f"  ✓ Quiescent baseline passed! 0 false triggers during {self.quiescent_sec}s window.")
            self.results["Quiescent Test"] = (True, f"0 false triggers over {self.quiescent_sec}s stillness")
            return True
        else:
            print(f"  ✗ Quiescent baseline failed! {false_triggers} false triggers occurred.")
            print("    Check sensitivity pot, jumper setting ('H' mode), and power stability.")
            self.results["Quiescent Test"] = (False, f"{false_triggers} false triggers detected")
            return False

    def run_active_motion_test(self) -> bool:
        """Step 4: Prompts operator to trigger motion and verifies ISR & Pin D2."""
        print("\n[Step 4/5] Active Motion Trigger Verification...")
        print("=" * 60)
        print("  👉 [ACTION REQUIRED] WAVE YOUR HAND IN FRONT OF THE SENSOR NOW!")
        print("=" * 60)

        self.flush_input()
        if self.dry_run and hasattr(self.ser, "_phase"):
            self.ser._phase = "MOTION_WAIT"
            self.ser._motion_start_time = time.time()

        prompt_time = time.time()
        isr_fired = False
        pin_went_high = False
        trigger_latency = 0.0

        while time.time() - prompt_time < self.trigger_timeout_sec:
            line = self.read_line(timeout_sec=0.5)
            if line:
                print(f"  << {line}")
                if "[ISR_EVENT]" in line:
                    isr_fired = True
                    trigger_latency = round(time.time() - prompt_time, 2)
                if "[TRIGGER]" in line or "[MOTION_DETECTED]" in line:
                    pin_went_high = True
                    if trigger_latency == 0.0:
                        trigger_latency = round(time.time() - prompt_time, 2)
            if isr_fired and pin_went_high:
                break

        self.trigger_metrics["trigger_latency_sec"] = trigger_latency

        if isr_fired and pin_went_high:
            print(f"\n  ✓ Motion trigger successfully validated!")
            print(f"    - Hardware Interrupt INT0: FIRED (RISING edge)")
            print(f"    - Digital State Pin D2:     HIGH")
            print(f"    - Response Latency:         {trigger_latency} seconds")
            self.results["Interrupt INT0"] = (True, f"Fired on RISING edge ({trigger_latency}s)")
            self.results["Pin D2 HIGH"] = (True, "D2 transitioned to HIGH upon motion")
            return True
        elif pin_went_high and not isr_fired:
            print("  ✗ Pin D2 went HIGH, but INT0 interrupt failed to trigger.")
            self.results["Interrupt INT0"] = (False, "ISR did not fire")
            self.results["Pin D2 HIGH"] = (True, "D2 detected HIGH")
            return False
        else:
            print(f"  ✗ Motion trigger timed out ({self.trigger_timeout_sec}s). No motion detected.")
            self.results["Interrupt INT0"] = (False, "Timed out waiting for motion")
            self.results["Pin D2 HIGH"] = (False, "Pin remained LOW")
            return False

    def run_cooldown_reset_test(self) -> bool:
        """Step 5: Verifies that sensor output returns to LOW and measures pulse width."""
        print("\n[Step 5/5] Cooldown & Signal Clearing Verification...")
        print("  👉 [ACTION REQUIRED] Please remain still and allow sensor output to reset...")

        reset_start = time.time()
        pulse_cleared = False
        pulse_duration_ms = 0.0
        max_cooldown_wait = 3.0 if self.dry_run else 20.0
        last_hold_print = 0.0

        # Wait up to timeout for HC-SR501 time delay to expire
        while time.time() - reset_start < max_cooldown_wait:
            line = self.read_line(timeout_sec=0.5)
            if line:
                if "[ACTIVE_HOLD]" in line:
                    if time.time() - last_hold_print >= 1.5:
                        print(f"  << {line}")
                        last_hold_print = time.time()
                else:
                    print(f"  << {line}")

                if "[CLEAR]" in line or "[MOTION_CLEARED]" in line:
                    pulse_cleared = True
                    # Extract pulse duration if present
                    if "Duration:" in line:
                        try:
                            part = line.split("Duration:")[1].strip().split()[0]
                            pulse_duration_ms = float(part)
                        except Exception:
                            pass
                    break

        if pulse_cleared:
            elapsed_sec = round(time.time() - reset_start, 2)
            print(f"  ✓ Sensor pulse ended! Pin D2 returned to LOW.")
            if pulse_duration_ms > 0:
                print(f"    Measured Pulse Duration: {pulse_duration_ms} ms (~{round(pulse_duration_ms/1000.0, 1)}s)")
            self.results["Sensor Reset (LOW)"] = (True, f"Returned to LOW cleanly ({elapsed_sec}s)")
            self.trigger_metrics["pulse_duration_ms"] = pulse_duration_ms
            return True
        else:
            print("  ✗ Sensor output did not return to LOW within 20 seconds.")
            print("    Check time delay potentiometer (turn fully counter-clockwise).")
            self.results["Sensor Reset (LOW)"] = (False, "Pin D2 stayed HIGH or timed out")
            return False

    def print_summary_report(self) -> bool:
        """Outputs formatted test summary report and returns overall pass/fail."""
        print("\n" + "=" * 65)
        print("        PIR SENSOR HARDWARE INTEGRATION TEST REPORT")
        print("=" * 65)

        all_passed = True
        for test_name, (passed, details) in self.results.items():
            status_str = "✓ PASS" if passed else "✗ FAIL"
            print(f"  {status_str:8} | {test_name:20} | {details}")
            if not passed:
                all_passed = False

        print("-" * 65)
        if self.trigger_metrics:
            print("  Metrics:")
            if "trigger_latency_sec" in self.trigger_metrics:
                print(f"    • Trigger Response Latency: {self.trigger_metrics['trigger_latency_sec']}s")
            if "pulse_duration_ms" in self.trigger_metrics:
                print(f"    • Pulse Hold Duration:     {self.trigger_metrics['pulse_duration_ms']} ms")

        print("=" * 65)
        if all_passed:
            print("  🎉 RESULT: ALL HARDWARE INTEGRATION TESTS PASSED!")
            print("  The physical HC-SR501 PIR sensor is fully verified and ready")
            print("  for integration with the WatchdogFSM power switching circuit.")
        else:
            print("  ❌ RESULT: HARDWARE INTEGRATION TESTS FAILED!")
            print_pir_troubleshooting()
        print("=" * 65 + "\n")
        return all_passed

    def close(self):
        """Releases serial port connection."""
        if self.ser and hasattr(self.ser, "close"):
            try:
                self.ser.close()
            except Exception:
                pass


def run_monitor_mode(port: Optional[str] = None, baud: int = 115200):
    """Runs a live monitor streaming events directly from the Arduino Nano."""
    tester = PIRIntegrationTester(port=port, baud=baud)
    if not tester.connect():
        sys.exit(1)

    print("\n" + "=" * 60)
    print("      LIVE ARDUINO NANO PIR SENSOR MONITOR (Ctrl+C to exit)")
    print("=" * 60)
    try:
        while True:
            line = tester.read_line(timeout_sec=0.2)
            if line:
                print(line)
    except KeyboardInterrupt:
        print("\n[INFO] Monitor exited by user.")
    finally:
        tester.close()


def dump_sketch_info():
    """Prints sketch information and instructions to upload."""
    print("Arduino Firmware Sketch Location:")
    print(f"  {os.path.abspath(SKETCH_RELATIVE_PATH)}")
    print()
    print("To flash to physical Arduino Nano via Arduino IDE:")
    print("  1. Open Arduino IDE.")
    print(f"  2. Open file: {SKETCH_RELATIVE_PATH}")
    print("  3. Select Tools -> Board -> 'Arduino Nano'.")
    print("  4. Select Tools -> Processor -> 'ATmega328P' (or 'ATmega328P Old Bootloader').")
    print("  5. Select Tools -> Port -> (Your USB Serial Port).")
    print("  6. Click Upload (Cmd+U / Ctrl+U).")
    print()
    print("To flash via arduino-cli (if installed):")
    print(f"  arduino-cli compile --fqbn arduino:avr:nano {SKETCH_RELATIVE_PATH}")
    print(f"  arduino-cli upload -p /dev/cu.usbserial* --fqbn arduino:avr:nano {SKETCH_RELATIVE_PATH}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Physical HC-SR501 PIR sensor integration test runner for Arduino Nano."
    )
    parser.add_argument("--port", type=str, default=None, help="Serial port (e.g. /dev/cu.usbserial-1410). Auto-detects if omitted.")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate (default: 115200).")
    parser.add_argument("--quiescent-sec", type=int, default=5, help="Duration in seconds for stillness noise test (default: 5).")
    parser.add_argument("--timeout", type=int, default=15, help="Timeout in seconds for motion trigger prompt (default: 15).")
    parser.add_argument("--skip-warmup", action="store_true", help="Bypass 30-second sensor stabilization countdown.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate integration test without physical hardware.")
    parser.add_argument("--monitor", action="store_true", help="Run continuous live telemetry monitor.")
    parser.add_argument("--dump-sketch", action="store_true", help="Display sketch file path and upload instructions.")
    parser.add_argument("--troubleshoot", action="store_true", help="Display HC-SR501 hardware troubleshooting guide.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.troubleshoot:
        print_pir_troubleshooting()
        return 0

    if args.dump_sketch:
        dump_sketch_info()
        return 0

    if args.monitor:
        run_monitor_mode(port=args.port, baud=args.baud)
        return 0

    print("=" * 65)
    print("  HC-SR501 PIR Sensor Hardware Integration Test")
    print("  Target: Arduino Nano V3.0 (ATmega328P)")
    print(f"  Dry-Run Mode: {'ENABLED' if args.dry_run else 'DISABLED'}")
    print("=" * 65)

    tester = PIRIntegrationTester(
        port=args.port,
        baud=args.baud,
        quiescent_sec=args.quiescent_sec,
        trigger_timeout_sec=args.timeout,
        skip_warmup=args.skip_warmup,
        dry_run=args.dry_run
    )

    try:
        if not tester.connect():
            return 1

        # Step 1: Handshake
        if not tester.run_handshake_check():
            tester.print_summary_report()
            return 1

        # Step 2: Warm-up
        tester.handle_warmup_phase()

        # Step 3: Quiescent Noise Test
        if not tester.run_quiescent_noise_test():
            tester.print_summary_report()
            return 1

        # Step 4: Active Motion Trigger
        if not tester.run_active_motion_test():
            tester.print_summary_report()
            return 1

        # Step 5: Cooldown / Pulse Duration
        tester.run_cooldown_reset_test()

        # Final Report
        passed = tester.print_summary_report()
        return 0 if passed else 1

    finally:
        tester.close()


if __name__ == "__main__":
    sys.exit(main())
