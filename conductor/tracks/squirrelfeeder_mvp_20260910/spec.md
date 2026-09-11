# Specification: SquirrelFeeder MVP Implementation

## 1. Overview & Objectives
The **SquirrelFeeder MVP** is a self-contained, battery-powered edge camera system designed for monitoring wildlife at a backyard feeder. The system pairs an ultra-low-power Arduino Nano watchdog with a Raspberry Pi Zero W media node to balance micro-amp sleep power consumption with 1080p video recording capabilities.

### Core Objectives
1. **Watchdog Node (Arduino Nano V3.0):** Maintains an ultra-low-power sleep state (`SLEEP_MODE_PWR_DOWN`, `< 50 µA`), wakes immediately on motion detected by an HC-SR501 PIR sensor, activates a high-side P-MOSFET to power on the Raspberry Pi Zero W, and monitors for a clean shutdown signal with a 60-second hardware timeout failsafe.
2. **Media Node (Raspberry Pi Zero W):** Boots quickly (with network radios disabled), verifies the presence of a removable USB flash drive, mounts it to `/mnt/usb_storage`, captures a 20-second 1080p MP4 video clip using the CSI camera, flushes filesystems, pulses a GPIO acknowledgment pin to the Arduino Nano, and executes a clean OS halt (`poweroff`).

---

## 2. Hardware Architecture & Electrical Connections
- **PIR Sensor:** HC-SR501 (VCC=5V, OUT=3.3V active-HIGH to Nano Pin D2 / INT0, Jumper=H Repeatable Trigger).
- **Power Switch:** P-Channel MOSFET driven by Nano Pin D8 (Active LOW turns on 5V rail to Pi Zero W).
- **Shutdown Acknowledgment:** Pi Zero W GPIO 25 (Pin 22) to Nano Pin D6 (Active HIGH signals shutdown complete).
- **Camera Module:** Raspberry Pi Camera Module (CSI ribbon).
- **Storage Device:** Removable USB flash drive (FAT32/exFAT via Micro-USB OTG).
- **Power Supply:** 5V USB Power Bank with low-draw keep-alive or always-on capability.

---

## 3. Functional Requirements

### 3.1 Watchdog Firmware (Arduino Nano)
- **Interrupt Handling:** Configured for `RISING` edge on `INT0` (Pin D2).
- **FSM States:**
  - `STATE_SLEEP`: Disables ADC (`ADCSRA = 0`), Brown-Out Detector, and enters `SLEEP_MODE_PWR_DOWN`.
  - `STATE_POWER_ON`: Sets D8 LOW to saturate P-MOSFET, turns on onboard activity LED, and transitions to wait state.
  - `STATE_WAIT_SHUTDOWN`: Polls D6 for active-HIGH shutdown ACK from Pi Zero W while ticking a 60-second hardware failsafe timer.
  - `STATE_POWER_OFF_DELAY`: Upon receiving D6 ACK, waits 5,000 ms to ensure Linux kernel completes disk unmount and halts CPU safely, then releases D8 HIGH (cutting power) and returns to `STATE_SLEEP`.
- **Failsafe Timeout:** If D6 does not assert HIGH within 60 seconds of power-on, the Nano cuts power immediately to protect the battery from an unresponsive or hung OS.

### 3.2 Media Node Pipeline (Raspberry Pi Zero W)
- **Fast-Boot Profile:** Disable Bluetooth (`dtoverlay=disable-bt`), Wi-Fi, HDMI (`tvservice -o`), and non-critical systemd services to achieve boot-to-recording latency under 15 seconds.
- **Storage Management:**
  - Locate USB block storage device (`/dev/sda1` or `/dev/sd*`).
  - If missing, abort immediately and signal shutdown ACK to prevent idle battery drain.
  - If present, mount to `/mnt/usb_storage` and verify write permissions.
- **Video Capture:**
  - Execute `rpicam-vid` / `libcamera-vid` to capture a 20-second 1080p30 H.264 video packaged directly as MP4 into `/mnt/usb_storage/videos/clip_YYYYMMDD_HHMMSS.mp4`.
- **Graceful Shutdown Handshake:**
  - Flush all pending writes (`sync`).
  - Unmount `/mnt/usb_storage`.
  - Assert GPIO 25 HIGH for 500 ms to trigger Nano shutdown detection.
  - Execute `sudo poweroff`.

---

## 4. Acceptance Criteria
1. Arduino Nano draws < 1 mA in deep sleep mode on modified/bench hardware.
2. Motion event on Pin D2 activates D8 LOW within 5 ms.
3. Pi Zero W boots, mounts USB storage, records a 20-second 1080p MP4 clip, and halts cleanly without corrupting the FAT32/exFAT filesystem.
4. When USB drive is absent, the Pi detects missing storage within 3 seconds, asserts GPIO 25, and powers down.
5. If the Pi hangs or fails to assert ACK, the Nano force-cuts power at 60 seconds.

---

## 5. Out of Scope for MVP
- Wi-Fi networking, MQTT alerting, and cloud uploads (AWS IoT Core / S3).
- Multi-sensor fusion (IR break-beam, radar, or BME280 integration).
- Live stream linger window (WebRTC/RTSP).
