# Minimum Viable Product (MVP) System Design Document

**Document Status:** Approved Draft  
**Target Hardware:**  
- **Watchdog:** Arduino Nano V3.0 (ATmega328P, 5V)  
- **Media Node:** Raspberry Pi Zero W + Raspberry Pi Camera Module (CSI)  
- **Sensor:** HC-SR501 PIR Motion Sensor  
- **Power:** 5V USB Power Bank  
- **Storage:** Removable USB Flash Drive (FAT32 / exFAT via Micro-USB OTG)  

**Associated Documents:**  
- [Requirements.md](./Requirements.md)  
- [Logical_Block_Diagram.md](./Logical_Block_Diagram.md)  
- [Nano_Watchdog_Firmware_Design.md](./Nano_Watchdog_Firmware_Design.md)  
- [Pi_Zero_Media_Node_Design.md](./Pi_Zero_Media_Node_Design.md)  

---

## 1.0 Executive Summary & MVP Scope

The **Minimum Viable Product (MVP)** proves out the core physical, electrical, and software chain of the Squirrel Feeder project before introducing network connectivity, cloud synchronization, or multi-sensor fusion. 

### 1.1 Core Mission
A self-contained, battery-powered edge device that:
1. Sleeps in an ultra-low-power standby state.
2. Wakes immediately upon detecting motion via an **HC-SR501 PIR sensor**.
3. Powers on the **Raspberry Pi Zero W** via a P-channel MOSFET power switch.
4. Initializes the camera and records a **20-second 1080p video clip** directly to a **removable USB flash drive**.
5. Performs a clean filesystem flush, signals the Arduino Nano, and executes a clean OS halt.
6. The Arduino Nano disconnects power to the Pi and returns to sleep for the next event.

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

### 1.2 Deliberate Non-Goals for MVP
- **No Wi-Fi / Bluetooth:** Radios are completely disabled to maximize boot speed and eliminate network timeout hangs.
- **No Multi-Sensor Fusion:** Single PIR sensor directly triggers the wake event.
- **No Cloud / MQTT Services:** Video files remain exclusively on the removable USB drive.
- **No Fallback Internal Recording:** If the USB drive is missing or unmounted, the device aborts recording immediately to preserve battery.

---

## 2.0 Hardware Architecture & Electrical Interconnect

### 2.1 Component Interconnect & Pinout

```
+---------------------+              +-----------------------+
|  HC-SR501 PIR       |              |  Arduino Nano V3.0    |
|  VCC (4.5V - 12V)   | ◄── 5V Rail  |  VIN / 5V             | ◄── 5V Rail
|  GND                | ──── GND     |  GND                  | ──── GND
|  OUT (3.3V Active-H)| ───────────► |  D2 (INT0)            |
+---------------------+              |  D8 (MOSFET Gate Ctrl)| ────┐
                                     |  D6 (Shutdown ACK In) | ◄─┐ │
                                     +-----------------------+   │ │
                                                                 │ │
+---------------------+              +-----------------------+   │ │
|  P-MOSFET Power Gate|              |  Raspberry Pi Zero W  |   │ │
|  Source (S)         | ◄── 5V Rail  |  5V (Pins 2 & 4)      | ◄─┼─┘ (Switched 5V)
|  Gate (G)           | ◄────────────┤  GND (Pins 6 & 9)     | ──┼── GND
|  Drain (D)          | ────────────►┤  GPIO 25 (Pin 22)     | ──┘ (Shutdown ACK)
+---------------------+              |  Micro-USB OTG Port   | ──► [ USB Flash Drive ]
                                     |  CSI Camera Port      | ──► [ Camera Module ]
                                     +-----------------------+
```

| Signal / Rail | Origin | Destination | Electrical Characteristics |
| :--- | :--- | :--- | :--- |
| **5V Rail (Always On)** | USB Power Bank | Nano 5V Pin, PIR VCC, MOSFET Source | Regulated 5.0 V DC |
| **GND** | USB Power Bank | Common Ground (Nano, Pi, PIR, MOSFET) | 0 V Reference |
| **PIR Trigger** | HC-SR501 OUT | Nano Pin D2 (`INT0`) | Active HIGH: 3.3V on motion |
| **MOSFET Gate** | Nano Pin D8 | Gate Driver Transistor | Active LOW to saturate P-MOSFET |
| **Switched 5V Rail**| MOSFET Drain | Pi Zero W 5V Pins (Pin 2, 4) | Powers on Pi when MOSFET conducts |
| **Shutdown ACK** | Pi Zero W GPIO 25 (Pin 22) | Nano Pin D6 | Active HIGH: 3.3V signal to cut power |

### 2.2 HC-SR501 Sensor Tuning & Setup

The HC-SR501 module contains hardware potentiometers and a jumper that must be set properly for edge wake-up:

```
          [ Jumper: Set to 'H' ]
           (Repeatable Trigger)
           ┌───┬───┐
           │ H │ L │
           └───┴───┘
         ┌───────────┐
         │ HC-SR501  │
         │  PIR PCB  │
         └───────────┘
          ( )     ( )
         Delay    Sensitivity
          Pot     Pot
```

1. **Trigger Mode Jumper:** Set to **`H` (Repeatable Trigger)**. When an animal stays within the sensor FOV, the output remains HIGH rather than pulsing repeatedly.
2. **Time Delay Potentiometer:** Turn **fully counter-clockwise** to set minimum delay (~3 seconds). The Arduino Nano firmware handles all event timing.
3. **Sensitivity Potentiometer:** Set midway to detect squirrels at 3 to 5 meters while minimizing false triggers from distant background movement.

### 2.3 Power Bank Considerations: Preventing Auto-Shutoff

> [!WARNING]
> **Power Bank Sleep Gotcha**: Most commercial USB power banks have an automatic low-current shutoff circuit that cuts 5V power if the load draws less than **50 mA to 100 mA** for 10 to 30 seconds.
>
> While the Pi Zero W is powered on, the system draws **~250 mA**, which keeps the power bank active. However, when the Pi shuts down and the Nano enters deep sleep, the current drops below the shutoff threshold.

#### Recommended Solutions for MVP Testing:
1. **Low-Current Mode Power Banks:** Use power banks featuring an explicit "always-on" or "trickle charge" mode (e.g., Voltaic Systems V-series, Nitecore NPB series, or Anker models activated by double-clicking the power button).
2. **Bench Supply / Powered Hub:** During software bring-up, power the 5V rail from a standard 5V wall adapter or powered USB hub to isolate software from power-bank cutoffs.
3. **Keep-Alive Load Pulse (Optional Hardware Hack):** Nano briefly pulses a 100-ohm resistor to GND for 100 ms every 8 seconds using the Watchdog timer to prevent power-bank sleep.

---

## 3.0 Arduino Nano MVP Firmware

The Arduino Nano serves as the power arbiter. It spends 99% of its life in `SLEEP_MODE_PWR_DOWN`, waking on an external interrupt from the PIR sensor.

### 3.1 State Flow

```
[ SLEEP_MODE_PWR_DOWN ] ◄─────────────────────────────────────────────┐
        │                                                             │
        │ PIR Pin D2 goes HIGH (INT0)                                 │
        ▼                                                             │
[ STATE_POWER_ON ]                                                    │
        │ Assert D8 LOW -> P-MOSFET Turns ON (Pi Boots)               │
        │ Start 60-second Failsafe Watchdog Timer                     │
        ▼                                                             │
[ STATE_WAIT_SHUTDOWN ]                                               │
        │                                                             │
        ├─► Pi asserts D6 HIGH (Shutdown Ready) ──┐                   │
        │                                         ▼                   │
        └─► Failsafe Timer Expires (>60 sec) ────►[ STATE_COOLDOWN ]  │
                                                        │             │
                                                        │ Delay 10s   │
                                                        │ Turn Off    │
                                                        │ MOSFET (D8) │
                                                        └─────────────┘
```

### 3.2 Complete MVP Arduino Firmware (`Nano_MVP_Watchdog.ino`)

```cpp
#include <avr/sleep.h>
#include <avr/interrupt.h>

// Pin Definitions
constexpr uint8_t PIN_PIR_INT      = 2;  // INT0 (HC-SR501 OUT)
constexpr uint8_t PIN_MOSFET_GATE  = 8;  // Active LOW (Turns on P-MOSFET)
constexpr uint8_t PIN_SHUTDOWN_ACK = 6;  // Input from Pi GPIO 25

// Timing Constraints
constexpr uint32_t HARDWARE_FAILSAFE_MS = 60000; // 60s hard power cutoff
constexpr uint32_t POST_SHUTDOWN_DELAY_MS = 5000; // 5s for Pi Linux halt
constexpr uint32_t COOLDOWN_REFRACTORY_MS = 10000; // 10s blind window

void wakeInterrupt() {
    // Interrupt Service Routine - wakes CPU from sleep mode
}

void enterDeepSleep() {
    // Power down ADC and Analog Comparator
    ADCSRA = 0;
    
    // Attach wake interrupt on rising edge of PIR sensor
    attachInterrupt(digitalPinToInterrupt(PIN_PIR_INT), wakeInterrupt, RISING);
    
    set_sleep_mode(SLEEP_MODE_PWR_DOWN);
    sleep_enable();
    
    // Disable Brown-Out Detector during sleep
    sleep_bod_disable();
    
    // Enter sleep mode
    sleep_cpu();
    
    // --- CPU SLEEPS HERE ---
    
    // Execution resumes here on wake
    sleep_disable();
    detachInterrupt(digitalPinToInterrupt(PIN_PIR_INT));
}

void setup() {
    // Configure pins
    pinMode(PIN_MOSFET_GATE, OUTPUT);
    digitalWrite(PIN_MOSFET_GATE, HIGH); // Start with MOSFET OFF (Active LOW)
    
    pinMode(PIN_SHUTDOWN_ACK, INPUT);
    pinMode(PIN_PIR_INT, INPUT);
}

void loop() {
    // 1. Enter deep sleep until PIR fires
    enterDeepSleep();
    
    // 2. Motion Detected -> Latch MOSFET ON to boot Raspberry Pi Zero W
    digitalWrite(PIN_MOSFET_GATE, LOW);
    uint32_t powerOnTime = millis();
    
    // 3. Monitor for Pi Shutdown ACK or Failsafe Timeout
    bool shutdownReceived = false;
    while ((millis() - powerOnTime) < HARDWARE_FAILSAFE_MS) {
        if (digitalRead(PIN_SHUTDOWN_ACK) == HIGH) {
            shutdownReceived = true;
            break;
        }
        delay(50);
    }
    
    // 4. Wait for Linux to finalize disk unmount and enter halt state
    delay(POST_SHUTDOWN_DELAY_MS);
    
    // 5. Cut power to Raspberry Pi Zero W
    digitalWrite(PIN_MOSFET_GATE, HIGH);
    
    // 6. Refractory Cooldown: Prevent immediate re-trigger while animal exits
    delay(COOLDOWN_REFRACTORY_MS);
}
```

---

## 4.0 Raspberry Pi Zero W MVP Software

The Raspberry Pi Zero W executes a lean Python recording script orchestrated by a dedicated `systemd` service.

### 4.1 Storage Setup & Mount Management

1. **Drive Format:** Format the USB flash drive as **FAT32** (or **exFAT**), labeled `SQUIRREL_USB`.
2. **Mount Point:** Mounted to `/mnt/usb` at boot.
3. **Mount Configuration (`/etc/fstab`):**
   ```fstab
   LABEL=SQUIRREL_USB  /mnt/usb  vfat  defaults,nofail,flush,noatime  0  0
   ```
   - `nofail`: Prevents boot hang if the USB drive is missing.
   - `flush`: Flushes file write buffers immediately to prevent corruption.

### 4.2 Missing USB Policy (Immediate Abort)

Per confirmed requirements, **if the USB drive is not detected or fails to mount, the Pi aborts recording immediately** to prevent draining the battery on unusable events:

```
[ Pi Boots ] ──► Check if /mnt/usb is mounted and writable
                      │
                      ├───► NO (Drive missing/corrupt)
                      │       │
                      │       ├─► Flash Activity LED rapidly (Error Pattern)
                      │       ├─► Assert GPIO 25 HIGH (Shutdown Signal)
                      │       └─► Invoke 'poweroff' immediately (~2s active time)
                      │
                      └───► YES (Drive ready)
                              │
                              └─► Proceed to 20-second video recording
```

### 4.3 Python MVP Video Recorder (`/usr/local/bin/record_mvp.py`)

```python
#!/usr/bin/env python3
"""
Squirrel Feeder MVP - Standalone Video Recorder
Records a 20-second H.264 video to removable USB storage and triggers poweroff.
"""

import os
import sys
import time
import subprocess
import RPi.GPIO as GPIO
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder

# Hardware Configuration
PIN_SHUTDOWN_ACK = 25       # BCM 25 (Pin 22) connected to Arduino Nano D6
USB_MOUNT_POINT = "/mnt/usb"
VIDEO_DIR = os.path.join(USB_MOUNT_POINT, "squirrel_videos")
RECORD_DURATION_SEC = 20

def setup_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(PIN_SHUTDOWN_ACK, GPIO.OUT, initial=GPIO.LOW)

def is_usb_mounted(path: str) -> bool:
    """Verifies that the USB storage device is mounted and writable."""
    if not os.path.ismount(path):
        return False
    # Test write permissions
    test_file = os.path.join(path, ".mount_test")
    try:
        with open(test_file, "w") as f:
            f.write("ok")
        os.remove(test_file)
        return True
    except Exception:
        return False

def signal_shutdown_and_halt():
    """Asserts shutdown signal to Nano and halts Linux."""
    print("[MVP] Asserting shutdown ACK to Arduino Nano...")
    GPIO.output(PIN_SHUTDOWN_ACK, GPIO.HIGH)
    time.sleep(0.5)
    print("[MVP] Executing systemctl poweroff...")
    subprocess.run(["systemctl", "poweroff"])
    sys.exit(0)

def main():
    setup_gpio()

    # 1. Verify Removable Storage
    if not is_usb_mounted(USB_MOUNT_POINT):
        print(f"[ERROR] USB mount at {USB_MOUNT_POINT} not found or not writable.")
        print("[MVP] Aborting session to preserve battery.")
        signal_shutdown_and_halt()

    # 2. Ensure Video Directory Exists
    os.makedirs(VIDEO_DIR, exist_ok=True)

    # 3. Generate Timestamped Filename
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_filepath = os.path.join(VIDEO_DIR, f"clip_{timestamp}.mp4")

    print(f"[MVP] Starting 20s recording to: {output_filepath}")

    # 4. Initialize Camera & Record 1080p30 H.264 Video
    try:
        picam2 = Picamera2()
        video_config = picam2.create_video_configuration(
            main={"size": (1920, 1080), "format": "RGB888"},
            controls={"FrameRate": 30}
        )
        picam2.configure(video_config)
        
        encoder = H264Encoder(bitrate=10000000) # 10 Mbps H.264
        picam2.start_recording(encoder, output_filepath)
        
        # Wait for the 20-second recording window
        time.sleep(RECORD_DURATION_SEC)
        
        picam2.stop_recording()
        picam2.close()
        print(f"[MVP] Recording completed successfully.")

    except Exception as e:
        print(f"[ERROR] Camera recording failed: {e}")

    # 5. Flush Filesystem Buffers
    print("[MVP] Flushing filesystem write cache...")
    os.sync()

    # 6. Signal Arduino Nano & Power Off
    signal_shutdown_and_halt()

if __name__ == "__main__":
    main()
```

### 4.4 Systemd Auto-Run Service (`/etc/systemd/system/squirrel-mvp.service`)

```ini
[Unit]
Description=Squirrel Feeder MVP Recording Service
DefaultDependencies=no
After=local-fs.target
Requires=local-fs.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/bin/record_mvp.py
StandardOutput=journal+console
StandardError=journal+console
Restart=no

[Install]
WantedBy=basic.target
```

---

## 5.0 Power Budget & Battery Longevity Analysis

### 5.1 Cycle Energy Consumption (Single Event)

A complete capture cycle consists of the following phases:

| Phase | Duration | Average Current @ 5V | Energy Consumed |
| :--- | :--- | :--- | :--- |
| **1. Pi Boot & OS Init** | 12.0 seconds | ~180 mA | 0.600 mAh |
| **2. USB Verification & Cam Init**| 1.5 seconds | ~220 mA | 0.092 mAh |
| **3. 1080p30 H.264 Recording** | 20.0 seconds | ~260 mA | 1.444 mAh |
| **4. Disk Sync & OS Shutdown** | 4.5 seconds | ~160 mA | 0.200 mAh |
| **Total Active Energy per Event** | **38.0 seconds** | **~221 mA avg** | **~2.34 mAh per trigger** |

### 5.2 Standby Power (Sleep)

- **Arduino Nano in Deep Sleep:** ~15 mA (unmodified stock clone) or **$< 50\,\mu\text{A}$** (power LED trace cut).
- **HC-SR501 Standby Current:** ~65 µA.
- **MOSFET Off-State Leakage:** $< 1\,\mu\text{A}$.
- **Total Standby Current (Optimized Board):** **$\approx 115\,\mu\text{A}$ (0.115 mA)**.

### 5.3 Battery Longevity on a 5000 mAh (18.5 Wh) USB Power Bank

Assuming 80% effective usable capacity (~4000 mAh net):

| Frequency | Daily Active Draw | Daily Standby Draw | Total Daily Draw | Estimated Longevity |
| :--- | :--- | :--- | :--- | :--- |
| **10 triggers / day** | 23.4 mAh | 2.76 mAh | 26.2 mAh | **~152 days (~5 months)** |
| **25 triggers / day** | 58.5 mAh | 2.76 mAh | 61.3 mAh | **~65 days (~2 months)** |
| **50 triggers / day** | 117.0 mAh | 2.76 mAh | 119.8 mAh | **~33 days (~1 month)** |

*(Note: If using an unmodified stock Nano board drawing ~15 mA during sleep, standby consumption will be ~360 mAh/day, limiting battery life to ~10 days regardless of triggers. Desoldering the power LED is highly recommended).*

---

## 6.0 Step-by-Step Bring-Up & Verification Guide

Follow this four-phase benchtop sequence to validate each subsystem independently before assembling the full enclosure.

```
+-------------------------------------------------------------------------------+
|                        MVP VERIFICATION PHASES                                |
|                                                                               |
|  [ Phase 1: Pi USB Capture ] ──► Validate Picamera2 records to USB drive      |
|              │                                                                |
|              ▼                                                                |
|  [ Phase 2: Nano MOSFET ]   ──► Validate Nano controls Pi power & timeout     |
|              │                                                                |
|              ▼                                                                |
|  [ Phase 3: PIR Integration] ──► Validate wave of hand boots & triggers Pi    |
|              │                                                                |
|              ▼                                                                |
|  [ Phase 4: Field Retrieval] ──► Unplug USB, verify playback on Mac/PC        |
+-------------------------------------------------------------------------------+
```

### Phase 1: Standalone Pi Zero W USB Recording
1. Connect the camera ribbon cable and insert the USB flash drive via the Micro-USB OTG adapter.
2. Power the Pi Zero W from a standard USB charger.
3. Manually execute `/usr/local/bin/record_mvp.py`.
4. Confirm:
   - File is created under `/mnt/usb/squirrel_videos/clip_<timestamp>.mp4`.
   - Recording lasts exactly 20 seconds.
   - Script triggers `poweroff` cleanly.

### Phase 2: Arduino Nano MOSFET Power Switching
1. Wire the P-channel MOSFET between the 5V power supply and the Pi Zero W 5V pins.
2. Connect Nano D8 to the MOSFET gate and D6 to Pi GPIO 25.
3. Power the Nano. Pull Nano D2 HIGH manually with a jumper wire to simulate a trigger.
4. Confirm:
   - MOSFET turns ON; Pi Zero W boots.
   - Pi records, asserts GPIO 25, and shuts down.
   - Nano detects GPIO 25 HIGH, waits 5 seconds, and cuts MOSFET power.

### Phase 3: PIR Sensor Trigger Integration
1. Wire HC-SR501 VCC to 5V, GND to GND, and OUT to Nano pin D2.
2. Set HC-SR501 jumper to `H` and turn time delay potentiometer fully counter-clockwise.
3. Allow the PIR sensor 30 seconds to stabilize after initial power.
4. Wave a hand in front of the lens.
5. Confirm complete autonomous sequence: Motion -> Pi boots -> 20s recording -> shutdown -> Nano sleeps.

### Phase 4: Removable Storage Verification (Mac/PC Playback)
1. After the device completes a cycle and powers down, unplug the USB flash drive.
2. Insert into a laptop (Mac/PC/Linux).
3. Confirm:
   - Volume mounts without filesystem error or repair prompts.
   - Video file `clip_<timestamp>.mp4` plays smoothly at 1080p30 with clear video quality.
