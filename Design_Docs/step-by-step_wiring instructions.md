# SquirrelFeeder: Step-by-Step Hardware Wiring Guide

A complete, beginner-friendly, step-by-step guide for wiring the **SquirrelFeeder** autonomous edge monitoring station. 

This guide details how to connect the **5V Power Source**, **Arduino Nano V3.0 (Watchdog Node)**, **High-Side P-Channel MOSFET Power Switch**, **Raspberry Pi Zero W (Media Node)**, and **HC-SR501 PIR Motion Sensor**.

---

## Table of Contents
1. [Core Design Concept: High-Side Switching](#1-core-design-concept-high-side-switching)
2. [Bill of Materials (BOM)](#2-bill-of-materials-bom)
3. [Component Pinouts & Identification](#3-component-pinouts--identification)
4. [Master Interconnect Schematic](#4-master-interconnect-schematic)
5. [Sequential Step-by-Step Wiring Instructions](#5-sequential-step-by-step-wiring-instructions)
   - [Step 1: Build the Common Ground Bus](#step-1-build-the-common-ground-bus-gnd)
   - [Step 2: Wire the Always-On +5V Power Rail](#step-2-wire-the-always-on-5v-power-rail)
   - [Step 3: Wire the P-MOSFET Gate & Pull-Up Resistor](#step-3-wire-the-p-mosfet-gate--pull-up-resistor)
   - [Step 4: Connect the Switched +5V Rail to the Raspberry Pi](#step-4-connect-the-switched-5v-rail-to-the-raspberry-pi)
   - [Step 5: Wire the HC-SR501 PIR Motion Sensor](#step-5-wire-the-hc-sr501-pir-motion-sensor)
   - [Step 6: Wire the Shutdown Acknowledgment Line](#step-6-wire-the-shutdown-acknowledgment-line)
6. [Pin-to-Pin Connection Matrix](#6-pin-to-pin-connection-matrix)
7. [Pre-Flight Multimeter Testing (Before Connecting the Pi)](#7-pre-flight-multimeter-testing-before-connecting-the-pi)
8. [Troubleshooting & Common Pitfalls](#8-troubleshooting--common-pitfalls)

---

## 1. Core Design Concept: High-Side Switching

To maximize battery life, the system keeps the power-hungry Raspberry Pi completely turned off until motion is detected. When the PIR sensor detects an animal, the Arduino Nano switches 5V power to the Pi.

```text
       [ +5V Battery Rail ]
                │
                ▼
        [ P-MOSFET Switch ] ◄── Controlled by Arduino Nano (Pin D8)
                │ (Switched +5V Rail)
                ▼
      [ Raspberry Pi Zero W ]
                │
                ▼
      [ Common Ground Rail ] ◄── Shared by ALL components (0V Reference)
```

### Why a High-Side P-Channel MOSFET?
- **Always Keep Grounds Connected:** If you disconnect the ground wire (low-side switching), the Raspberry Pi's ground floats up to 5V. Current would then backfeed through the GPIO signaling pins into the Arduino, damaging both boards.
- **Switch the Positive Rail:** High-side switching cuts the positive (+5V) wire while keeping the ground continuous between the Battery, Arduino, Sensor, and Raspberry Pi.
- **Active-LOW Control Logic:**
  - `D8 = HIGH (5V)`: MOSFET is **OFF** (Pi is completely unpowered).
  - `D8 = LOW (0V)`: MOSFET is **ON** (Pi boots and records).

---

## 2. Bill of Materials (BOM)

| Component | Quantity | Purpose / Recommendation |
| :--- | :--- | :--- |
| **Arduino Nano V3.0** | 1 | ATmega328P 5V microcontroller (Watchdog Node). |
| **Raspberry Pi Zero W** | 1 | Linux Media Node (Records 1080p video clips). |
| **Raspberry Pi Camera Module** | 1 | CSI v2 or v3 camera with 15-pin ribbon cable. |
| **HC-SR501 PIR Sensor** | 1 | Passive Infrared motion detector. |
| **Logic-Level P-Channel MOSFET** | 1 | TO-220 package (e.g., **NDP6020P**, **FQP27P06**, **IRLML6402**). Must turn fully ON at $V_{GS} = -4.5\text{V}$ to $-5\text{V}$. |
| **10 kΩ Resistor** | 1 | Gate pull-up resistor (holds MOSFET OFF by default). |
| **220 Ω to 1 kΩ Resistor** | 1 | Gate current-limiting resistor (protects Arduino pin D8). |
| **5V USB Power Bank** | 1 | Battery source with always-on / low-current mode. |
| **Micro-USB OTG Flash Drive** | 1 | Removable FAT32/exFAT storage for captured videos. |
| **Breadboard & Jumper Wires** | — | Prototyping board and male-to-male / male-to-female jumper wires. |

---

## 3. Component Pinouts & Identification

### A. P-Channel MOSFET (Standard TO-220 Package)
Look at the front of the MOSFET (where the part number is printed, metal heatsink tab in the back, pins pointing downward):

```text
       ┌───────────────┐
       │   [METAL TAB] │  (Internally connected to Drain)
       │               │
       │   P-MOSFET    │
       │   (Front)     │
       └───────┬───────┘
           │   │   │
           │   │   └── Pin 3: SOURCE (S) ──> Connected to Always-On +5V
           │   └────── Pin 2: DRAIN (D)  ──> Connected to Pi 5V (Switched Rail)
           └────────── Pin 1: GATE (G)   ──> Connected to Arduino Pin D8
```

> [!IMPORTANT]
> Always verify the pinout against your specific MOSFET datasheet if using a different package (e.g., SOT-23 or a pre-assembled breakout board).

---

### B. Arduino Nano V3.0 Key Pins
- **`5V`**: Always-on regulated 5V power input.
- **`GND`**: System common ground.
- **`D2` (`INT0`)**: Interrupt 0 input for PIR motion detection (Active HIGH 3.3V pulse).
- **`D6`**: Input for Raspberry Pi shutdown acknowledgment pulse (Active HIGH 3.3V pulse).
- **`D8`**: Active-LOW output to MOSFET Gate (`LOW` = Power ON, `HIGH` = Power OFF).
- **`D13`**: Onboard activity LED.

---

### C. Raspberry Pi Zero W 40-Pin Header
Pins are numbered from 1 to 40. Pin 1 is the 3.3V pin in the inner corner near the microSD card slot:

```text
                        Pin 1 (3.3V) [ o  o ] Pin 2 (5V Power Input)  <── Switched 5V Rail
                                     [ o  o ] Pin 4 (5V Power Input)
                                     [ o  o ] Pin 6 (GND)             <── Common GND
                                     [ o  o ] Pin 8 (GPIO 14)
                                     [ o  o ] Pin 10 (GPIO 15)
                                     [ o  o ] Pin 12 (GPIO 18)
                                     [ o  o ] Pin 14 (GND)
                                     [ o  o ] Pin 16 (GPIO 23)
                                     [ o  o ] Pin 18 (GPIO 24)
                                     [ o  o ] Pin 20 (GND)
    Shutdown ACK Out ──> Pin 22 (GPIO 25) [ o  o ] Pin 21 (GPIO 9)
                                     [ ...  ]
```

---

### D. HC-SR501 PIR Sensor
Remove the plastic white Fresnel dome if needed to check the pin labels under the header:

```text
     ┌────────────────────────┐
     │      HC-SR501 PCB      │
     │                        │
     │  [Time]  [Sensitivity] │
     │   Pot         Pot      │
     └───────┬───┬───┬────────┘
             │   │   │
             │   │   └── GND  (Ground)
             │   └────── OUT  (3.3V Motion Trigger -> Nano D2)
             └────────── VCC  (4.5V - 12V -> Connect to +5V)
```
- **Trigger Jumper:** Set jumper to **`H` (Repeatable Trigger)**.
- **Time Delay Potentiometer:** Turn **fully counter-clockwise** (~3 seconds minimum delay).
- **Sensitivity Potentiometer:** Set to roughly **midway** (3 to 5 meters detection range).

---

## 4. Master Interconnect Schematic

```text
+5V Always-On Rail
  [Battery +5V] ───┬───────────────────────┬────────────────────────┬──────────────────────┐
                   │                       │                        │                      │
               [Nano 5V]               [PIR VCC]            [MOSFET Source (S)]            │
                                                                    │                      │
                                                            ┌───────┴───────┐              │
                                                            │  10kΩ Pull-up │              │
                                                            │   Resistor    │              │
                                                            └───────┬───────┘              │
                                                                    │                      │
  [Nano Pin D8] ───[ 220Ω - 1kΩ Resistor ]─────────────────────────► [MOSFET Gate (G)]     │
                                                                    │                      │
                                                            [MOSFET Drain (D)]             │
                                                                    │ (Switched 5V Rail)   │
                                                                    ▼                      │
                                                            [Pi Zero W Pin 2/4]            │
                                                                                           │
Signal Lines:                                                                              │
  [PIR OUT]     ───────────────────────────────────────────► [Nano Pin D2]                 │
  [Pi GPIO 25]  ───────────────────────────────────────────► [Nano Pin D6]                 │
                                                                                           │
GND Rail (Common Reference)                                                                │
  [Battery GND] ───┬───────────────────────┬────────────────────────┬──────────────────────┘
                   │                       │                        │
               [Nano GND]               [PIR GND]            [Pi Zero Pin 6]
```

---

## 5. Sequential Step-by-Step Wiring Instructions

Follow these steps in strict numerical order on your breadboard or proto-board.

### Step 1: Build the Common Ground Bus (`GND`)
1. Run a black wire from your **Battery GND / USB Negative terminal** to the blue/negative ground bus rail on your breadboard.
2. Connect a jumper wire from **Arduino Nano `GND`** to the ground bus rail.
3. Connect a jumper wire from **Raspberry Pi Zero W Pin 6 (`GND`)** to the ground bus rail.
4. Connect a jumper wire from **HC-SR501 PIR `GND`** to the ground bus rail.

> [!TIP]
> Confirm that all ground pins meet at this same ground bus. Never leave any device ground unconnected!

---

### Step 2: Wire the Always-On +5V Power Rail
1. Run a red wire from your **Battery +5V / USB Positive terminal** to the red/positive power bus rail on your breadboard.
2. Connect a jumper wire from the +5V bus rail to the **Arduino Nano `5V` pin**.
3. Connect a jumper wire from the +5V bus rail to the **HC-SR501 PIR `VCC` pin**.
4. Connect a jumper wire from the +5V bus rail directly to the **MOSFET Source (S)** pin (Pin 3 on standard TO-220).

> [!CAUTION]
> **DO NOT** connect the always-on +5V rail directly to the Raspberry Pi! The Pi must only receive power from the MOSFET Drain.

---

### Step 3: Wire the P-MOSFET Gate & Pull-Up Resistor
1. Insert your **$10\text{ k}\Omega$ resistor** between the **MOSFET Gate (G)** and the **MOSFET Source (S)** (+5V rail).
   - *Why:* This pulls the gate up to 5V when the Arduino starts up or sleeps, guaranteeing the MOSFET is completely turned **OFF** by default.
2. Insert your **$220\text{ }\Omega$ to $1\text{ k}\Omega$ resistor** in series:
   - One lead connects to **Arduino Nano Pin `D8`**.
   - The other lead connects directly to the **MOSFET Gate (G)**.
   - *Why:* This protects the Arduino output pin from capacitive inrush currents when switching.

---

### Step 4: Connect the Switched +5V Rail to the Raspberry Pi
1. Connect a jumper wire from the **MOSFET Drain (D)** pin (Pin 2 on standard TO-220) to the **Raspberry Pi Zero W Pin 2 or Pin 4 (`5V`)**.
   - *Result:* When Arduino asserts `D8 = LOW`, current flows from the Battery $\rightarrow$ Source $\rightarrow$ Drain $\rightarrow$ Raspberry Pi Pin 2/4.

---

### Step 5: Wire the HC-SR501 PIR Motion Sensor
1. Connect the **HC-SR501 `OUT` pin** (center pin) directly to **Arduino Nano Pin `D2`**.
   - *Why:* Pin `D2` is hardware interrupt `INT0` on the ATmega328P. When motion occurs, the sensor sends a 3.3V pulse, waking the Arduino from deep sleep (`SLEEP_MODE_PWR_DOWN`).

---

### Step 6: Wire the Shutdown Acknowledgment Line
1. Connect a jumper wire from **Raspberry Pi Zero W Pin 22 (`GPIO 25`)** to **Arduino Nano Pin `D6`**.
   - *Why:* After capturing the 20-second video and safely flushing the USB flash drive buffers, the Pi's Python daemon sends a 3.3V pulse on GPIO 25. The Arduino detects this on D6, waits a 5-second grace window for Linux to halt cleanly, and then de-asserts D8 (cutting power).

---

## 6. Pin-to-Pin Connection Matrix

| # | Wire Origin | Wire Destination | Signal / Function | Electrical Notes |
| :---: | :--- | :--- | :--- | :--- |
| **1** | Battery (+5V) | Breadboard +5V Bus Rail | Main Power Bus | Regulated 5.0 V DC |
| **2** | Battery (GND) | Breadboard GND Bus Rail | Common System Ground | 0.0 V Reference |
| **3** | Breadboard +5V | Arduino Nano `5V` | Always-on Nano power | Continuous ~15-30 mA (sleep: < 1 mA) |
| **4** | Breadboard GND | Arduino Nano `GND` | Nano Ground | Ground reference |
| **5** | Breadboard +5V | HC-SR501 `VCC` | PIR Sensor power | 4.5V - 12V supply range |
| **6** | Breadboard GND | HC-SR501 `GND` | PIR Ground | Ground reference |
| **7** | HC-SR501 `OUT` | Arduino Nano `D2` (`INT0`) | Motion Wake Trigger | 3.3V active-high pulse |
| **8** | Breadboard +5V | MOSFET **Source (S)** | MOSFET Input Power | High-side power delivery |
| **9** | MOSFET **Source (S)** | MOSFET **Gate (G)** | 10 kΩ Pull-up Resistor | Holds MOSFET in cut-off state (OFF) |
| **10**| Arduino Nano `D8` | MOSFET **Gate (G)** | Power Gate Ctrl (via 220Ω) | Active LOW (LOW = ON, HIGH = OFF) |
| **11**| MOSFET **Drain (D)** | Pi Zero W **Pin 2 or 4 (5V)**| Switched 5V Power Rail | Energizes Pi on demand (~250 mA) |
| **12**| Breadboard GND | Pi Zero W **Pin 6 or 9 (GND)**| Pi Zero Ground | Common ground |
| **13**| Pi Zero W **Pin 22 (GPIO 25)**| Arduino Nano `D6` | Shutdown ACK Signal | 3.3V active-high pulse signals OS halt |

---

## 7. Pre-Flight Multimeter Testing (Before Connecting the Pi)

> [!WARNING]
> Do NOT connect the Raspberry Pi until you have completed this 4-step validation test with a digital multimeter!

1. **Disconnect the Raspberry Pi:** Leave the wire coming from MOSFET Drain unconnected to the Pi.
2. **Flash the Watchdog Firmware:** Upload the sketch [`Arduino_Nano.ino`](file:///Users/davidkester/Workspace/SquirrelFeeder/Arduino_Nano/Arduino_Nano.ino) to the Arduino.
3. **Measure Default Cutoff State (OFF):**
   - Connect the multimeter **Black Probe** to Common GND.
   - Connect the multimeter **Red Probe** to the MOSFET Drain (D).
   - *Expected Reading:* **$0.00\text{ V}$**. (If you see $5\text{ V}$, your pull-up resistor is missing or your MOSFET pinout is reversed).
4. **Measure Triggered State (ON):**
   - Wave your hand in front of the HC-SR501 PIR sensor.
   - The Arduino onboard LED (Pin 13) should turn ON.
   - The multimeter reading on MOSFET Drain (D) should immediately jump to **$+5.0\text{ V}$**.
   - After 60 seconds (failsafe timer), the LED should turn OFF and the voltage should drop back to **$0.00\text{ V}$**.
5. **Connect the Pi:** Once verified, turn off the battery, connect MOSFET Drain to Pi Pin 2/4, plug in the USB flash drive and camera, and power back on!

---

## 8. Troubleshooting & Common Pitfalls

| Symptom | Probable Cause | Corrective Action |
| :--- | :--- | :--- |
| **Raspberry Pi turns ON immediately and never powers off** | Gate pull-up resistor missing or pinout swapped between Drain and Source. | Check the 10 kΩ resistor between Gate and Source. Verify that Source is on +5V and Drain feeds the Pi. |
| **Raspberry Pi never powers on when motion occurs** | Arduino pin D8 not asserting LOW, or MOSFET is not a "Logic-Level" device. | Standard MOSFETs require 10V $V_{GS}$ to conduct. Ensure you use a logic-level P-MOSFET (e.g., NDP6020P) that conducts fully at -4.5V. |
| **Power bank shuts down after 30 seconds of sleep** | Power bank auto-shutoff triggered by low standby current draw (< 50 mA). | Use a power bank with an "Always-On" or "Low-Current" mode, or power via a 5V bench adapter. |
| **Arduino resets when the Raspberry Pi boots** | Inrush current to the Pi's decoupling capacitors causes a momentary 5V rail sag. | Add a $470\text{ }\mu\text{F} - 1000\text{ }\mu\text{F}$ electrolytic capacitor across the main 5V and GND rail near the battery input. |
| **Pi reports corrupted SD card / filesystem errors** | Power is being cut before the OS cleanly halts. | Verify Pi GPIO 25 signals Nano D6 and that Nano waits the 5-second `POST_SHUTDOWN_DELAY_MS` before cutting D8. |
