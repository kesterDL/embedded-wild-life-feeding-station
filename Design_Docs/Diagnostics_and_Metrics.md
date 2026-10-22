# Diagnostics, Telemetry & Visualization Architecture

This document defines the metrics collection, hardware power diagnostics, filename schemas, and data visualization tools for the Squirrel Feeder media capture subsystem.

---

## 1. Overview & Architecture

Because the Squirrel Feeder operates as an intermittent, battery-powered edge capture node that cold-boots on motion triggers, comprehensive telemetry is required to:
1. Monitor **cold-boot latency** to ensure animals are not missed before recording starts.
2. Detect **power rail sag and under-voltage brownouts** (`vcgencmd get_throttled`).
3. Track **subsystem health** across camera capture, disk mounting, and MP4 containerization.
4. Visualize historical behavior across bench and field testing cycles through an **offline-first interactive dashboard**.

```
  [ Motion Trigger ] ──► [ Arduino Nano Watchdog ]
                                 │ (Power Gate MOSFET)
                                 ▼
                     [ Raspberry Pi Cold Boot ]
                                 │
     ┌───────────────────────────┴───────────────────────────┐
     ▼                                                       ▼
[ System Telemetry ]                                [ Storage Manager ]
 • Cold-boot uptime (/proc/uptime)                   • Monotonic sequence counter
 • Power throttling (vcgencmd get_throttled)         • Filename formatter
     │                                                       │
     └───────────────────────────┬───────────────────────────┘
                                 ▼
                    [ Media Orchestrator ]
                     • Appends to lifecycle.log
                     • Saves clip_{SEQ}_boot{UPTIME}s_{PWR}.mp4
                                 │
                                 ▼
             [ Visualization Tooling & Dashboard ]
              • visualize_metrics.py
              • fetch_and_watch.py --visualize
```

---

## 2. Telemetry Schema (`lifecycle.log`)

Every capture cycle records an entry to `lifecycle.log`. This file resides on the FAT32 boot partition (`/boot/firmware/lifecycle.log` or `/boot/lifecycle.log`), allowing developers to inspect logs directly by plugging the microSD card into a PC or syncing via Wi-Fi.

### CSV Column Reference

| Column | Type | Description | Example |
| :--- | :--- | :--- | :--- |
| `timestamp` | ISO String | System clock timestamp at cycle completion | `2026-10-15 15:24:28` |
| `uptime_s` | Float | Cold-boot latency from power-on until capture initiation (seconds) | `11.70` |
| `record_s` | Float | Active camera capture duration (seconds) | `21.80` |
| `mux_s` | Float | MP4 containerization / packaging duration (seconds) | `4.20` |
| `total_cycle_s` | Float | Total awake duration from trigger until unmount/shutdown | `26.00` |
| `status` | String | Execution outcome (`SUCCESS`, `CAMERA_ERROR`, `STORAGE_ERROR`) | `SUCCESS` |
| `video_file` | String | Generated MP4 filename | `clip_00001_boot12s_pwrOK.mp4` |
| `throttled` | String | Raw output from `vcgencmd get_throttled` | `throttled=0x50005` |

---

## 3. Hardware Power Diagnostics (`vcgencmd get_throttled`)

Under-voltage brownouts significantly degrade system performance, prolong boot times, and trigger camera sensor failures. The Raspberry Pi PMIC firmware exposes a 32-bit hardware status bitmask:

### Bitmask Decoding Reference

| Bit | Hex Value | Name | Description | Impact |
| :---: | :---: | :--- | :--- | :--- |
| **0** | `0x1` | **Active Under-voltage** | 5V supply rail is currently **< 4.63V** | High risk of sensor crash or spontaneous reset |
| **1** | `0x2` | **Active ARM Capped** | ARM frequency capped | Reduced single-thread throughput |
| **2** | `0x4` | **Active Throttling** | CPU core frequency actively throttled (e.g. 1.2 GHz $\to$ 600 MHz) | **Boot latency increases by +40% to +55%** |
| **3** | `0x8` | **Active Temp Limit** | Soft temperature limit exceeded | Core frequency throttled |
| **16** | `0x10000` | **Under-voltage Occurred** | Supply drooped < 4.63V at least once since boot | Indicates power rail sag during inrush load |
| **17** | `0x20000` | **Freq Capping Occurred** | Frequency was capped since boot | Indicates historical throttling event |
| **18** | `0x40000` | **Throttling Occurred** | Throttling occurred since boot | Core performance degraded during cycle |
| **19** | `0x80000` | **Temp Limit Occurred** | Temperature limit reached since boot | Historical thermal event |

### Common States

- **`0x0` (`pwrOK`)**: Clean power supply. Voltage strictly maintained above 4.75V. CPU operates at full clock speed.
- **`0x50005` (`pwrWARN`)**: Active Under-voltage + Active Throttling + Historical Under-voltage + Historical Throttling. The power supply or MOSFET power path is dropping excessive voltage under load.

---

## 4. Video Filename Diagnostic Schema

To prevent ambiguous filenames caused by the Raspberry Pi's lack of a battery-backed Real-Time Clock (RTC), all video files follow a monotonic diagnostic naming convention:

$$\mathbf{clip\_\{SEQ:05d\}\_boot\{UPTIME\}s\_\{PWR\}.mp4}$$

### Components

1. **`{SEQ}`**: Monotonic 5-digit sequence counter (e.g. `00001`, `00042`), persisted in `/var/lib/squirrelfeeder/sequence` or `~/.squirrel_sequence`.
2. **`boot{UPTIME}s`**: Total boot latency in seconds (rounded integer) from `/proc/uptime`.
3. **`{PWR}`**: Power status badge:
   - `pwrOK`: Normal voltage (`throttled=0x0` or `N/A`).
   - `pwrWARN`: Under-voltage or throttling detected (`throttled > 0`).

*Example:* `clip_00042_boot12s_pwrOK.mp4`

---

## 5. Interactive Visualization Dashboard

The dashboard generator (`Pi_Zero/scripts/visualize_metrics.py`) produces a single, self-contained HTML file (`metrics_dashboard.html`) with inlined Chart.js assets, enabling field diagnostics without an active internet connection.

### Dashboard Panels & Visualizations

1. **Top KPI Summary Cards**:
   - Total Cycles & Cold Boot Triggers
   - Overall Capture Success Rate (%)
   - Power Brownout Frequency (%)
   - Average Startup Latency comparison (Clean Power vs. Brownout)
2. **Panel 1 — Start-up Boot Latency vs. Power State**:
   - Bar chart of cold-boot uptime across cycles.
   - Points colored emerald green (`pwrOK`) or red/amber (`pwrWARN`) with tooltips showing exact hex throttling masks.
3. **Panel 2 — Cycle Phase Timing Breakdown**:
   - Stacked bar chart showing the composition of each cycle: Boot Uptime + Video Recording Duration + MP4 Muxing Duration.
4. **Panel 3 — Reliability & Failure Distribution**:
   - Donut chart categorizing `SUCCESS`, `CAMERA_ERROR`, and `STORAGE_ERROR` events.
5. **Panel 4 — Recording Payload Sizes**:
   - Chart displaying video file sizes (MB), highlighting truncated or 0-MB files resulting from sensor drops.
6. **Panel 5 — Searchable Lifecycle Event Log**:
   - Filterable data table supporting text search, status filtering, and power state filtering.

---

## 6. CLI Usage & Tooling

### Standalone Dashboard Generation
```bash
# Generate dashboard for default Wild_Life_Recordings directory
python3 Pi_Zero/scripts/visualize_metrics.py

# Generate and immediately open in default browser
python3 Pi_Zero/scripts/visualize_metrics.py --open

# Generate from a custom log path
python3 Pi_Zero/scripts/visualize_metrics.py --log /path/to/lifecycle.log --output report.html --open
```

### Integrated with Sync Tool (`fetch_and_watch.py`)
```bash
# Pull recordings from remote Pi over Wi-Fi and automatically launch the dashboard
python3 Pi_Zero/scripts/fetch_and_watch.py --pull --visualize

# Generate and open dashboard from local recordings without pulling
python3 Pi_Zero/scripts/fetch_and_watch.py --visualize

# Generate dashboard without opening browser
python3 Pi_Zero/scripts/fetch_and_watch.py --visualize --no-open
```
