# Technical Design Document: Raspberry Pi Media Node Software

**Document Status:** Draft  
**Target Hardware:** Raspberry Pi Zero W (Broadcom BCM2835 ARM11 @ 1 GHz, 512 MB LPDDR2, 2.4 GHz 802.11n Wi-Fi)  
**Associated Documents:**  
- [Requirements.md](./Requirements.md)  
- [Logical_Block_Diagram.md](./Logical_Block_Diagram.md)  
- [Nano_Watchdog_Firmware_Design.md](./Nano_Watchdog_Firmware_Design.md)  

---

## 1.0 Executive Summary & Architectural Role

The **Raspberry Pi Zero W** operates as the **Media & Network Node** in the dual-architecture wildlife feeder system. While the Arduino Nano serves as the ultra-low-power watchdog continuously evaluating sensors, the Pi Zero W remains completely unpowered until a validated positive trigger occurs.

When powered by the Nano's MOSFET gate, the Pi Zero W boots, initializes the camera, executes hardware-accelerated video recording, captures telemetry from the Nano, synchronizes data with network storage, serves an optional on-demand live stream linger window, and executes a clean shutdown.

```
+-----------------------------------------------------------------------------------+
|                           EDGE TIER: MEDIA NODE (Pi Zero W)                       |
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  |                           PIPELINE ORCHESTRATOR                             |  |
|  |      Coordinates Boot -> Ingest -> Capture -> Sync -> Linger -> Shutdown    |  |
|  +-----+-------------------+-------------------+-------------------+----------+  |
|        |                   |                   |                   |              |
|        v                   v                   v                   v              |
|  +-----------+     +---------------+     +---------------+     +---------------+  |
|  |  CAMERA   |     |   WATCHDOG    |     |    STORAGE    |     | NOTIFICATION  |  |
|  |  SERVICE  |     |    BRIDGE     |     |    MANAGER    |     |   PUBLISHER   |  |
|  | (Picamera2|     | (UART Telemetry|    | (SD Ring Buf, |     | (MQTT Alerts, |  |
|  |  H.264 HW)|     |  & GPIO ACKs) |     |  NAS/S3 Sync) |     |  AWS IoT Core)|  |
|  +-----------+     +---------------+     +---------------+     +---------------+  |
|        │                   │                     │                     │          |
|        v                   v                     v                     v          |
|  [CSI Camera]      [Arduino Nano]       [Local NAS / S3]      [Mosquitto Broker]  |
+-----------------------------------------------------------------------------------+
```

---

## 2.0 Hardware Platform & Operating Environment

### 2.1 Compute & Camera Hardware Analysis

| Component | Specification | Software Implication |
| :--- | :--- | :--- |
| **SoC / CPU** | Broadcom BCM2835 (ARM1176JZF-S @ 1.0 GHz, Single Core) | Single-threaded bottlenecks; avoid heavy CPU encoding or complex edge models. |
| **RAM** | 512 MB LPDDR2 (Shared with GPU) | Memory budget requires lean Python/asyncio footprint (<80 MB RAM total). |
| **GPU / VideoCore IV** | Dedicated H.264 V4L2 Hardware Encoder & ISP | Direct GPU hardware encoding enables full 1080p30 / 720p30 with <15% CPU load. |
| **Storage** | MicroSD Card (UHS-I) | Susceptible to corruption if power is cut during write; requires OverlayFS/read-only root. |
| **Wireless** | 2.4 GHz 802.11 b/g/n Wi-Fi | Intermittent signal outdoors requires store-and-forward local buffering. |

#### Camera Module Evaluation: CSI vs. ESP32-S3-CAM
- **ESP32-S3-CAM (Alternative Evaluated):** Lacks hardware H.264 video encoding. It relies on MJPEG software compression over DVP/SPI, yielding high compression artifacts, low framerates (10–15 fps at 1080p), and severe dynamic range degradation.
- **Raspberry Pi Camera Module V2 / V3 (Selected):** Direct CSI-2 ribbon connection interfaces with the VideoCore IV hardware ISP. 
  - **Phase 1/2 Baseline:** Pi Camera Module V2 (8MP Sony IMX219) or V3 (12MP Sony IMX708 with HDR and autofocus). Delivers crisp 1080p30 H.264 with minimal CPU overhead.
  - **Night Evolution:** Pi Camera NoIR (No Infrared filter) paired with an 850nm or 940nm external IR LED illuminator for nocturnal wildlife monitoring.

### 2.2 Fast Boot & Filesystem Hardening

Because the Pi Zero W boots on demand, minimizing boot latency is essential to begin recording before the animal departs:

1. **OS Selection:** Raspberry Pi OS Lite (32-bit Bullseye or Bookworm minimal headless).
2. **Systemd Optimization:** Mask unnecessary services (`bluetooth.service`, `modemmanager.service`, `cups.service`, `avahi-daemon.service`, `triggerhappy.service`). Target boot time to recording: **10 to 14 seconds**.
3. **Power-Cut Immune Filesystem (OverlayFS):**
   - Root filesystem (`/`) mounted **Read-Only** with an OverlayFS RAM layer (`tmpfs`).
   - Volatile logs and runtime state stored in `/run` and `/tmp` (`tmpfs`).
   - Dedicated persistent data partition (`/data`) formatted as `ext4` with aggressive commit intervals (`commit=60`) exclusively dedicated to the video ring buffer.
   - Prevents SD card corruption even if the Arduino Nano cuts power prematurely.

---

## 3.0 Extensible Modular Architecture

The software is structured as an **asynchronous event-driven pipeline**. Components are decoupled using dependency injection and abstract interfaces, allowing features to be toggled or upgraded across phases.

```
+-----------------------------------------------------------------------------------+
|                             CORE SERVICE PIPELINE                                 |
|                                                                                   |
|  [Power On] ──► systemd starts squirrel-media.service                              |
|                       │                                                           |
|                       ▼                                                           |
|  1. [WatchdogBridge]  ──► Set GPIO 24 HIGH (Signal "Pi Booted" to Nano)          |
|                       ──► Query Nano via UART for EventTelemetry JSON             |
|                       │                                                           |
|                       ▼                                                           |
|  2. [CameraService]   ──► Initialize Picamera2 GPU encoder                        |
|                       ──► Record H.264 video to /data/spool/                      |
|                       │                                                           |
|                       ▼                                                           |
|  3. [TelemetryService]──► Combine Nano sensor metrics with Pi OS metrics          |
|                       │                                                           |
|                       ▼                                                           |
|  4. [StorageManager]  ──► Commit to local SD ring buffer (Spooler)                |
|                       ──► Upload video & telemetry to NAS / S3 (if online)        |
|                       │                                                           |
|                       ▼                                                           |
|  5. [Notification]    ──► Publish MQTT alert to 'alerts/motion' (if online)       |
|                       │                                                           |
|                       ▼                                                           |
|  6. [LingerWindow]    ──► If requested, serve WebRTC/RTSP live stream (3-5 min)   |
|                       │                                                           |
|                       ▼                                                           |
|  7. [ShutdownHandler] ──► Flush caches, set GPIO 25 HIGH (SHUTDOWN_ACK)           |
|                       ──► Execute 'systemctl poweroff'                            |
+-----------------------------------------------------------------------------------+
```

---

## 4.0 Phased Software Roadmap

### 4.1 Phase 1: Baseline MVP (Simple Subset)

**Objective:** Achieve reliable standalone recording and power gating without requiring network connectivity.

- **Execution Flow:**
  1. Service starts automatically on boot via systemd.
  2. Asserts GPIO 24 HIGH to confirm boot to the Nano.
  3. Spawns `Picamera2` pipeline and records a fixed 20-second clip (1080p30 H.264, 12 Mbps) directly to `/data/spool/event_<timestamp>.mp4`.
  4. Flushes the video file to disk and updates the local FIFO ring buffer.
  5. Asserts GPIO 25 HIGH (`SHUTDOWN_ACK`) to signal the Nano that operations are complete.
  6. Invokes clean Linux shutdown (`poweroff`).
- **Dependencies:** `python3`, `python3-libcamera`, `python3-picamera2`, `RPi.GPIO`. Zero external network requirements.

### 4.2 Phase 2: Local Network Integration & Telemetry

**Objective:** Add local network synchronization, rich sensor telemetry, MQTT alerting, and on-demand live streaming.

- **New Capabilities:**
  - **UART Telemetry Ingestion:** Reads the 20-byte `EventTelemetry` packet from the Arduino Nano over `/dev/serial0` (trigger source, confidence, BME280 temperature, battery drop).
  - **Asynchronous Storage Dispatch:** Uploads captured MP4 clips and telemetry to the local NAS using the recommended stateless transfer protocol.
  - **Store-and-Forward Spooler:** If Wi-Fi is down or weak, clips are stored in the local SD ring buffer and automatically synchronized during future boots.
  - **Local MQTT Alerting:** Publishes structured event payloads to the local Mosquitto broker:
    - Topic: `alerts/motion` (Immediate event notification).
    - Topic: `telemetry/feeder-1` (Combined sensor, battery, and Pi system metrics).
  - **Wake-on-Event + Linger Window:** Once recording completes, if configured or requested via MQTT, the Pi keeps the camera active and serves a low-latency live stream for 3 to 5 minutes before shutting down.

### 4.3 Phase 3: Cloud Integration & Advanced Analytics

**Objective:** Seamlessly bridge the local pipeline into cloud services and edge intelligence.

- **New Capabilities:**
  - **Direct AWS S3 Storage:** Multi-part S3 upload using boto3 / presigned URLs.
  - **AWS IoT Core Integration:** MQTT with X.509 mutual TLS authentication and AWS Device Shadow state synchronization.
  - **Keyframe / Thumbnail Generation:** Uses `ffmpeg` or `libcamera` raw capture to extract a lightweight JPEG thumbnail ($< 50\text{ KB}$) for instant push notifications.
  - **Edge Classification Hook:** Optional lightweight TensorFlow Lite model (e.g., MobileNetV2 SSD) classifying subjects (e.g., `squirrel`, `bird`, `raccoon`, `empty`) and tagging the event metadata.

---

## 5.0 Video Duration & Trigger Policy

Wildlife interactions at a feeder vary from brief 5-second fly-bys to prolonged 3-minute feeding sessions. The recording engine employs an extensible `ITriggerPolicy`:

```python
class ITriggerPolicy:
    def should_continue_recording(self, elapsed_seconds: float) -> bool:
        """Determines whether the video recorder should keep capturing."""
        raise NotImplementedError
```

### 5.1 Policy Implementations

#### 1. `FixedDurationPolicy` (Phase 1 Baseline)
- Captures for a static, configurable window (e.g., $T_{fixed} = 20\text{ seconds}$).
- Predictable battery consumption and predictable video file sizes (~30 MB per clip at 12 Mbps).

#### 2. `SensorExtendedPolicy` (Phase 2/3 Dynamic)
- Begins with a minimum base window (e.g., 15 seconds).
- While recording, the Pi monitors the Arduino Nano's trigger line (or polls UART heartbeat).
- If the Nano detects ongoing sensor activity (Break Beam or Radar triggers), recording is extended in 10-second increments.
- **Safety Ceiling ($T_{max} = 60\text{ seconds}$):** Imposes a hard maximum cutoff to prevent rogue subjects (or stuck sensors) from completely draining the battery in a single session.

---

## 6.0 Local Storage Protocol: Trade-Off Analysis & Recommendation

The system requires transferring captured videos from the Pi Zero W to local network storage (NAS). The protocol must be resilient to intermittent outdoor Wi-Fi and safe against power shutdown hangs.

### 6.1 Protocol Comparison

| Criteria | Option 1: SMB / CIFS | Option 2: NFS Mount | Option 3: rsync / SFTP | Option 4: Local S3 (MinIO) / REST API |
| :--- | :--- | :--- | :--- | :--- |
| **Architecture** | Kernel Filesystem Mount | Kernel Filesystem Mount | User-space Push Process | Stateless HTTP/REST API Push |
| **Wi-Fi Dropout Resilience** | **Poor.** Kernel blocks I/O operations indefinitely. | **Poor.** Can lock system calls even with `soft` mount. | **High.** User-space handles timeouts and retries cleanly. | **Excellent.** Stateless HTTP requests with built-in retry. |
| **Shutdown Hang Risk** | **High.** `umount` hangs during poweroff if NAS drops. | **High.** RPC timeouts delay shutdown for minutes. | **Zero.** Process killed cleanly; no filesystem unmount. | **Zero.** No mounts involved; instant clean exit. |
| **CPU Overhead (ARM11)**| Moderate | Low | High (SSH encryption overhead) | Very Low (Standard HTTP/TLS) |
| **Cloud Migration Path** | None (Requires rewrite for AWS) | None (Requires rewrite for AWS) | Custom scripting needed | **100% Code Parity with AWS S3 via boto3 / SDK** |

### 6.2 Recommendation & Technical Rationale

> [!IMPORTANT]
> **Recommendation:** Adopt **Option 4: Stateless S3-Compatible API (MinIO) or Lightweight REST Upload**, backed by an offline local SD ring buffer.

#### Architectural Rationale:
1. **Elimination of Kernel Mount Deadlocks:** Mounting SMB or NFS at the Linux OS level (`/etc/fstab`) on an intermittent, battery-powered outdoor edge device is hazardous. If the outdoor Wi-Fi drops or the NAS reboots, kernel-level unmount operations hang during `poweroff`, causing the Pi to stay awake until the Arduino Nano's hardware timer forcibly cuts power.
2. **Direct Bridge to AWS S3 (Phase 3):** MinIO is an open-source, lightweight S3-compatible object storage server that runs on any home NAS or server. By implementing the S3 API in Phase 2 via standard Python libraries (`boto3` or `urllib3`), **zero code changes** are required when migrating from local NAS to AWS S3 in Phase 3—only the endpoint URL and credentials change.
3. **Resilient Local Spooling:** Uploads are executed asynchronously in user space. If an upload fails or times out (5-second timeout), the video remains in the local SD ring buffer and the Pi proceeds immediately to shutdown without delaying.

---

## 7.0 Store-and-Forward Local Ring Buffer

To guarantee network fault tolerance (Non-Functional Requirement 4.3), video files are never streamed directly to the network without being secured on local storage first.

### 7.1 Spooler Architecture

```
/data/
  ├── spool/                      # Active recording directory
  │     └── rec_20260908_142030.mp4
  ├── archive/                    # Secured ring buffer
  │     ├── vid_20260908_142030.mp4
  │     └── vid_20260908_142030.json (Telemetry metadata)
  └── spooler.db                  # SQLite sync catalog
```

### 7.2 Synchronization Lifecycle

```
[ Video Recorded ] ──► Commit MP4 to /data/archive/
                             │
                             ▼
                 Record metadata in SQLite
                 Status: PENDING_UPLOAD
                             │
            ┌────────────────┴────────────────┐
            ▼                                 ▼
      [ Wi-Fi Online ]                [ Wi-Fi Offline ]
            │                                 │
     Push to NAS / S3                 Keep in Local Spool
     Status: UPLOADED                         │
            │                                 ▼
            ▼                       Upload on subsequent
    Evict oldest files               successful boot
    when quota > 80%
```

### 7.3 Quota & FIFO Eviction Engine
- **Capacity Budget:** The `/data` partition is assigned a maximum quota (e.g., $8.0\text{ GB}$, holding ~250 clips).
- **Eviction Priority:**
  1. Files marked `UPLOADED` are deleted first (oldest first) when storage usage exceeds 80%.
  2. If storage exceeds 95% and un-uploaded files exist, the oldest `PENDING_UPLOAD` files are deleted to ensure new events can always be recorded.

---

## 8.0 Watchdog Handshake & Telemetry Integration

### 8.1 Hardware Pin Mapping (Pi Zero W Header)

| Pi Pin | GPIO Number | Function | Connected To (Arduino Nano) | Electrical Level |
| :--- | :--- | :--- | :--- | :--- |
| **Pin 8** | GPIO 14 | `UART0_TXD` | Nano Pin D0 (RXD) | 3.3V Direct into 5V Nano |
| **Pin 10** | GPIO 15 | `UART0_RXD` | Nano Pin D1 (TXD) via 1k/2k Divider | 3.3V Logic Safe |
| **Pin 16** | GPIO 23 | Reserved | Future Nano Interrupt Line | 3.3V Logic |
| **Pin 18** | GPIO 24 | `PI_STATUS_HEARTBEAT` | Nano Pin D7 | 3.3V into Nano D7 |
| **Pin 22** | GPIO 25 | `SHUTDOWN_ACK` | Nano Pin D6 | 3.3V into Nano D6 |

### 8.2 UART Protocol & Telemetry Schema

Immediately after asserting `PI_STATUS_HEARTBEAT` HIGH, the Pi queries the Nano over UART at 115200 baud:

```
Pi Zero W ──► "REQ_METRICS\n" ──► Arduino Nano
Pi Zero W ◄── JSON Payload   ◄── Arduino Nano
```

#### Nano Ingested Telemetry (from Nano Firmware Design):
```json
{
  "boot": 142,
  "trig": 3,
  "conf": 88,
  "dt_ms": 420,
  "temp": 33.4,
  "hum": 58.2,
  "v_rest": 4120,
  "v_load": 3840,
  "fp_rej": 14,
  "lat_ms": 62
}
```

#### Merged Edge Telemetry Payload (Published to MQTT `telemetry/feeder-1`):
```json
{
  "device_id": "feeder-edge-01",
  "timestamp": "2026-09-08T14:20:30Z",
  "watchdog": {
    "boot_count": 142,
    "trigger_mask": 3,
    "confidence_score": 88,
    "sensor_delta_ms": 420,
    "ambient_temp_c": 33.4,
    "ambient_humidity_pct": 58.2,
    "vbat_resting_mv": 4120,
    "vbat_loaded_mv": 3840,
    "false_positives_filtered": 14,
    "fusion_latency_ms": 62
  },
  "media_node": {
    "boot_duration_sec": 11.4,
    "wifi_rssi_dbm": -64,
    "cpu_temp_c": 42.8,
    "video_duration_sec": 20.0,
    "video_file_name": "vid_20260908_142030.mp4",
    "video_size_bytes": 29841200,
    "storage_free_mb": 6420
  }
}
```

---

## 9.0 Linger Window & Live Stream Server

To satisfy **Functional Requirement 3.4 (Asynchronous Live Feed)**, the system implements a "Wake-on-Event + Linger" window:

1. **Trigger Phase:** Video recording completes and is spooled to disk.
2. **Linger Activation:**
   - The Pi publishes an MQTT state update to `status/feeder-1`: `{"state": "LINGERING", "stream_url": "rtsp://192.168.1.150:8554/live"}`.
   - Starts a lightweight RTSP/WebRTC server (e.g., `mediamtx` or Picamera2 MJPEG HTTP server).
   - Starts a 3-to-5 minute countdown timer.
3. **Connection Monitoring:**
   - If an on-demand dashboard client connects, the stream is served live.
   - If no client connects within 60 seconds of recording completion (or once all connected clients disconnect), the linger window terminates early to conserve battery.
4. **Shutdown Transition:** The linger server closes, buffers are flushed, and the shutdown sequence executes.

---

## 10.0 Verification & Implementation Roadmap

### 10.1 Verification Stages

1. **Stage 1: Standalone Hardware H.264 Benchmark**
   - Verify `Picamera2` pipeline on Pi Zero W. Confirm 1080p30 H.264 recording produces $<15\%$ CPU utilization and zero dropped frames.
2. **Stage 2: Power Gate & GPIO Handshake Timing**
   - Wire Pi GPIO 24/25 to Nano pins D7/D6.
   - Measure full cycle: Nano MOSFET latch -> Pi boot -> 20s recording -> clean OS halt -> Nano power cut. Verify zero filesystem corruption over 50 consecutive cycles.
3. **Stage 3: Offline Ring Buffer & Quota Eviction Test**
   - Disable Wi-Fi. Trigger 20 consecutive recordings. Verify all clips store cleanly in `/data/archive/` and FIFO eviction operates when quota is exceeded.
   - Re-enable Wi-Fi. Verify store-and-forward synchronizes all pending clips to local NAS/MinIO.
4. **Stage 4: UART Telemetry Integration**
   - Test serial request-response across the 1k/2k resistor divider. Verify JSON checksum integrity and schema validation on the Pi.
5. **Stage 5: Live Stream Linger Test**
   - Connect VLC / browser dashboard to the linger RTSP/HTTP stream during the 3-minute window. Verify smooth stream delivery and graceful shutdown upon client disconnect.
