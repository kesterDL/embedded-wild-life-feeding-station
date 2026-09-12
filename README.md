# SquirrelFeeder: Embedded Wildlife Monitoring Station

[![Hardware](https://img.shields.io/badge/Hardware-Arduino_Nano_%2B_Pi_Zero_W-blue.svg)](#hardware-architecture)
[![Firmware](https://img.shields.io/badge/Firmware-ATmega328P_C%2B%2B17-green.svg)](#1-firmware-unit-tests-arduino-nano)
[![Media Node](https://img.shields.io/badge/Media_Node-Python_3.9%2B-orange.svg)](#2-python-media-pipeline-unit-tests-pi-zero-w)
[![SDD Framework](https://img.shields.io/badge/Workflow-Spec--Driven_Development-purple.svg)](#spec-driven-development-conductor)

An autonomous, battery-powered edge camera system engineered to monitor a backyard wildlife feeding station. The system balances ultra-low-power standby consumption with high-definition video capture by leveraging an asymmetric **Dual-Hardware Architecture**:

- **Watchdog Node (Arduino Nano V3.0):** Sleeps continuously in `SLEEP_MODE_PWR_DOWN` (< 50 µA), wakes immediately on motion detected by an HC-SR501 PIR sensor, latches a high-side P-MOSFET to deliver 5V power to the Linux media node, and enforces a 60-second hardware failsafe timer.
- **Media Node (Raspberry Pi Zero W):** Boots on demand, mounts a removable USB flash drive, captures a 20-second 1080p @ 25 fps MP4 clip via CSI camera module, flushes filesystem buffers, pulses a GPIO shutdown acknowledgment to the Nano, and halts the OS cleanly before power is cut.

---

## Hardware Architecture & Interconnect

```
+-----------------------------------------------------------------------------------+
|                                  MVP EDGE SYSTEM                                  |
|                                                                                   |
|  [ 5V USB Power Bank ]                                                            |
|          │                                                                        |
|          ├──────────────────────────────► [ HC-SR501 PIR ]                        |
|          │                                       │ (Motion Output: 3.3V Pulse)    |
|          │                                       ▼                                |
|          ├──────────────────────────────► [ Arduino Nano V3.0 (Always On / Sleep) ]|
|          │                                       │                                |
|          │                                       ├─► D8 (Gate): Asserts Power ON  |
|          │                                       │◄─ D6 (Ack):  Receives Shutdown |
|          ▼                                       │                                |
|   [ P-MOSFET Switch ] ◄──────────────────────────┘                                |
|          │ (Switched 5V Rail)                                                     |
|          ▼                                                                        |
|   [ Raspberry Pi Zero W ]                                                         |
|          ├─► [ CSI Ribbon ] ───────► [ Pi Camera Module ]                         |
|          └─► [ Micro-USB OTG ] ────► [ Removable USB Flash Drive (FAT32/exFAT) ]  |
+-----------------------------------------------------------------------------------+
```

### Pin Mapping

| Signal | Origin | Destination | Electrical Characteristics |
| :--- | :--- | :--- | :--- |
| **PIR Motion Trigger** | HC-SR501 OUT | Arduino Nano Pin D2 (`INT0`) | Active-HIGH 3.3V pulse on motion |
| **MOSFET Gate Control**| Arduino Nano Pin D8 | P-MOSFET Gate Driver | Active-LOW turns ON switched 5V rail |
| **Shutdown Acknowledgment** | Pi Zero W GPIO 25 (Pin 22) | Arduino Nano Pin D6 | Active-HIGH 3.3V pulse signals OS halt |
| **Camera Interface** | Pi Camera Module v2/v3 | Pi Zero W CSI Port | 15-pin ribbon to VideoCore IV ISP |
| **Storage** | USB Flash Drive | Pi Zero W Micro-USB OTG | Mounted to `/mnt/usb_storage` |

---

## Repository Structure

```text
.
├── Arduino_Nano/               # Watchdog Firmware
│   ├── Arduino_Nano.ino        # Main Arduino sketch & interrupt bindings
│   ├── include/
│   │   ├── ArduinoMock.h       # Mock platform for host-side unit testing
│   │   └── WatchdogFSM.h       # Finite state machine declarations
│   ├── integ_test_scripts/     # Isolated hardware integration test scripts
│   │   ├── test_pir_sensor.ino # Standalone Arduino Nano firmware for PIR testing
│   │   └── test_pir_integration.py # Host test runner, handshake, & diagnostics
│   ├── src/
│   │   └── WatchdogFSM.cpp     # State machine implementation & power logic
│   └── tests/
│       ├── test_pir_integration_script.py # Test runner unit tests
│       └── test_watchdog_fsm.cpp # Host unit tests (C++17)
├── Pi_Zero/                    # Media Node Software
│   ├── scripts/
│   │   ├── install.sh          # Deployment script for /opt/squirrelfeeder
│   │   ├── optimize_os.sh      # OS boot latency and power optimizations
│   │   ├── squirrel-record.service # Systemd fast-boot oneshot unit
│   │   └── test_camera_integration.py # Standalone hardware camera integration test
│   ├── src/
│   │   ├── camera_service.py   # rpicam-vid / libcamera-vid wrapper
│   │   ├── orchestrator.py     # Master boot-to-halt lifecycle daemon
│   │   ├── storage_manager.py  # USB drive detection, mount, and sync
│   │   └── watchdog_bridge.py  # GPIO 25 shutdown ACK signaling
│   └── tests/
│       ├── test_camera_integration.py
│       ├── test_camera_service.py
│       ├── test_orchestrator.py
│       ├── test_storage_manager.py
│       └── test_watchdog_bridge.py
├── Design_Docs/                # Architectural Specifications
│   ├── Logical_Block_Diagram.md
│   ├── MVP_System_Design.md
│   ├── Nano_Watchdog_Firmware_Design.md
│   ├── Pi_Zero_Media_Node_Design.md
│   └── Requirements.md
└── conductor/                  # Spec-Driven Development Artifacts
    ├── index.md                # Project context handshake
    ├── product.md              # Product definition & vision
    ├── tech-stack.md           # Technology stack documentation
    ├── workflow.md             # TDD and development workflow guidelines
    └── tracks/                 # Track implementation plans and specs
```

---

## Running Automated Tests

Both the embedded C++ firmware and the Python media pipeline include comprehensive unit test suites that run locally without physical hardware attached.

### 1. Firmware Unit Tests (Arduino Nano)

The watchdog firmware's finite state machine is decoupled from AVR hardware via [`ArduinoMock.h`](Arduino_Nano/include/ArduinoMock.h). It compiles and runs natively using `clang++` or `g++`:

```bash
# Compile and run the test harness
clang++ -std=c++17 -DUNIT_TEST \
  -IArduino_Nano/include \
  Arduino_Nano/src/WatchdogFSM.cpp \
  Arduino_Nano/tests/test_watchdog_fsm.cpp \
  -o test_runner && ./test_runner && rm -f test_runner
```

**Validated Behaviors:**
- D8 gate defaults to HIGH (Power OFF) and D2/D6 initialize as inputs.
- PIR motion interrupt transitions the state machine to `STATE_POWER_ON` and pulls D8 LOW.
- Signals are held active during Pi execution.
- Receiving D6 ACK triggers a 5-second OS halt settling grace period before cutting power.
- 60-second failsafe hardware timer force-cuts power if the Pi freezes or fails to ACK.

### 2. Python Media Pipeline Unit Tests (Pi Zero W)

Run the Python unit test suite using Python's built-in `unittest` runner:

```bash
python3 -m unittest discover -s Pi_Zero/tests/ -v
```

**Validated Behaviors:**
- Storage discovery prioritizes partitions (`/dev/sda1`) over whole disks (`/dev/sda`).
- Clean buffer sync (`os.sync()`) and filesystem unmounting before shutdown.
- Graceful battery-saving abort when USB media is absent (`StorageNotFoundError`).
- Camera command assembly and hardware error handling.
- GPIO 25 pulse signaling and full lifecycle orchestration.

### 3. Dry-Run Lifecycle Simulation

You can simulate the complete media pipeline on your local development machine using the `--dry-run` flag (bypasses the final `poweroff` command):

```bash
python3 -m Pi_Zero.src.orchestrator --dry-run
```

### 4. Hardware Camera Integration Test (Pi Zero W)

To verify physical CSI camera hardware functionality on the Raspberry Pi Zero W without engaging the storage mounting or watchdog shutdown sequences, run the standalone integration test script:

```bash
# Standard 20-second test: Detects sensor, captures 20s 1080p @ 25 fps video, stops camera, verifies file
python3 Pi_Zero/scripts/test_camera_integration.py

# Optional: customize duration (in seconds) or output destination
python3 Pi_Zero/scripts/test_camera_integration.py --duration 20 --output /tmp/test_clip.mp4

# Check-only mode (validates sensor detection without recording)
python3 Pi_Zero/scripts/test_camera_integration.py --check-only

# Dry-run mode (validates workflow simulation on host machine)
python3 Pi_Zero/scripts/test_camera_integration.py --dry-run
```

> [!TIP]
> **Why 1080p @ 25 fps on the Pi Zero W?**
> On Raspberry Pi OS (`libcamera` / `rpicam-vid`), camera pipeline and ISP processing run in user space on the Pi Zero's single-core 1.0 GHz ARM11 processor. At 1080p30, the single-core CPU operates near 100% saturation, which causes dropped frames from the sensor. Capping capture at **25 fps** reduces CPU overhead by ~20%, completely eliminating dropped frames and ensuring smooth, stutter-free playback.

#### Smooth Playback & MP4 Containerization:
- **On the Pi Zero:** `rpicam-vid` outputs raw H.264 elementary streams (`.h264`). To automatically package captures into standard ISO MP4 containers with constant PTS timestamps directly on the Pi Zero, install `MP4Box`:
  ```bash
  sudo apt update && sudo apt install -y gpac
  ```
- **On macOS (1-Click Fetch & Watch):** Use the included helper script on your Mac to pull the latest recording from the Pi, encapsulate it with uniform 25 fps timestamps via `ffmpeg`, and launch it directly in QuickTime Player:
  ```bash
  python3 scripts/fetch_and_watch.py
  ```

### 5. Hardware PIR Sensor Integration Test (Arduino Nano)

To test the physical HC-SR501 PIR sensor in complete isolation on a physical Arduino Nano—verifying the pyroelectric warm-up stabilization, quiescent baseline noise immunity, INT0 (Pin D2) rising-edge hardware interrupt, digital state transitions, and pulse duration without powering on the Raspberry Pi—use the standalone integration test suite:

#### Step A: Flash the Standalone Test Firmware to the Nano
Open [`Arduino_Nano/integ_test_scripts/test_pir_sensor.ino`](Arduino_Nano/integ_test_scripts/test_pir_sensor.ino) in the Arduino IDE (or upload via `arduino-cli`) and flash it to the physical Arduino Nano:
- Holds MOSFET Gate (Pin D8) HIGH to ensure the Raspberry Pi remains safely unpowered.
- Configures Pin D2 (`INT0`) as INPUT with RISING edge interrupt.
- Mirrors motion detection to onboard LED (Pin D13) for instant visual feedback.

#### Step B: Run the Host Integration Test Runner
Connect the Arduino Nano via USB to your Mac, PC, or Pi, and run:

```bash
# Auto-detects connected Arduino Nano serial port and runs guided test:
python3 Arduino_Nano/integ_test_scripts/test_pir_integration.py

# Skip 30s warm-up if sensor is already warmed up:
python3 Arduino_Nano/integ_test_scripts/test_pir_integration.py --skip-warmup

# Run live continuous event monitor:
python3 Arduino_Nano/integ_test_scripts/test_pir_integration.py --monitor

# View hardware wiring and potentiometer tuning guide:
python3 Arduino_Nano/integ_test_scripts/test_pir_integration.py --troubleshoot

# Dry-run mode (runs simulation without hardware attached):
python3 Arduino_Nano/integ_test_scripts/test_pir_integration.py --dry-run
```

---

## Using `Pi_Zero/scripts` (Deployment & Optimization)

The [`Pi_Zero/scripts`](Pi_Zero/scripts/) directory contains automated scripts to prepare and configure Raspberry Pi OS Lite on the Pi Zero W.

### Step 1: Optimize OS for Fast Boot and Low Power

Because the Pi Zero W boots only when an animal visits, cold-boot latency must be minimized. Run [`optimize_os.sh`](Pi_Zero/scripts/optimize_os.sh) as root:

```bash
sudo ./Pi_Zero/scripts/optimize_os.sh
```

**What this script does:**
1. **Masks Unnecessary Services:** Disables background daemons not needed on an edge camera (`bluetooth.service`, `avahi-daemon.service`, `triggerhappy.service`, `ModemManager.service`, `apt-daily.service`).
2. **Configures `/boot/config.txt`:**
   - Disables onboard Bluetooth (`dtoverlay=disable-bt`) and Wi-Fi (`dtoverlay=disable-wifi`).
   - Removes boot delays (`boot_delay=0`, `disable_splash=1`, `initial_turbo=30`).
   - Enables HDMI blanking (`hdmi_blanking=2`) to save ~25 mA.
3. **Hardware Power Savings:** Adds `/usr/bin/tvservice -o` to `/etc/rc.local` to shut off the HDMI transmitter completely.
4. **Ensures Mountpoints:** Creates `/mnt/usb_storage` directory for USB drives.

> [!NOTE]
> Reboot the Raspberry Pi after running `optimize_os.sh` for kernel overlay changes to take effect.

### Step 2: Install and Enable the Service

Install the recording orchestrator as a systemd service using [`install.sh`](Pi_Zero/scripts/install.sh):

```bash
sudo ./Pi_Zero/scripts/install.sh
```

**What this script does:**
1. Copies the `Pi_Zero` package to `/opt/squirrelfeeder/Pi_Zero`.
2. Installs `gpac` (`MP4Box`) for native MP4 container muxing.
3. Installs [`squirrel-record.service`](Pi_Zero/scripts/squirrel-record.service) to `/etc/systemd/system/squirrel-record.service`.
4. Reloads the systemd daemon and enables the service to launch automatically upon boot.

### Service Inspection & Troubleshooting

- **Check Service Status:**
  ```bash
  systemctl status squirrel-record.service
  ```
- **View Execution Logs:**
  ```bash
  journalctl -u squirrel-record.service -e
  ```
- **Manually Trigger a Recording Run:**
  ```bash
  sudo systemctl start squirrel-record.service
  ```

---

## Flashing the Arduino Nano Watchdog

1. Open [`Arduino_Nano/Arduino_Nano.ino`](Arduino_Nano/Arduino_Nano.ino) in the Arduino IDE or compile via `arduino-cli`:
   ```bash
   arduino-cli compile --fqbn arduino:avr:nano:cpu=atmega328old Arduino_Nano/
   arduino-cli upload -p /dev/ttyUSB0 --fqbn arduino:avr:nano:cpu=atmega328old Arduino_Nano/
   ```
2. **HC-SR501 Sensor Hardware Configuration:**
   - **Trigger Mode Jumper:** Set to **`H` (Repeatable Trigger)** so the signal stays HIGH during motion.
   - **Time Delay Potentiometer:** Turn **fully counter-clockwise** to minimum delay (~3 seconds); the Arduino handles event timing.
   - **Sensitivity Potentiometer:** Set midway (3–5 meters detection radius).

> [!WARNING]
> **Power Bank Auto-Shutoff Gotcha:** Standard commercial power banks shut off their 5V output if current drops below 50–100 mA for more than 15–30 seconds. In deep sleep, the Nano draws under 1 mA. Use a power bank with an "Always-On" or low-current mode (e.g. Voltaic V-series, Nitecore NPB), or use a dedicated 5V bench supply during bring-up.

---

## Spec-Driven Development (Conductor)

This repository follows the **Spec-Driven Development (SDD)** protocol managed by the [Conductor](https://github.com/gemini-cli-extensions/conductor) plugin:
- Track status and history are registered in [`conductor/tracks.md`](conductor/tracks.md).
- Active track plan: [`conductor/tracks/squirrelfeeder_mvp_20260910/plan.md`](conductor/tracks/squirrelfeeder_mvp_20260910/plan.md).
- Architectural requirements: [`conductor/product.md`](conductor/product.md) and [`conductor/tech-stack.md`](conductor/tech-stack.md).

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
