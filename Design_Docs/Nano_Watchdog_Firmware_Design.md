# Technical Design Document: Arduino Nano Watchdog Firmware

**Document Status:** Draft  
**Target Hardware:** Arduino Nano V3.0 (Microchip ATmega328P @ 16 MHz, CH340G USB Bridge, 5V Logic)  
**Associated Documents:**

- [Requirements.md](./Requirements.md)
- [Logical_Block_Diagram.md](./Logical_Block_Diagram.md)

---

## 1.0 Executive Summary & Architectural Role

The **Arduino Nano V3.0** operates as the dedicated **Watchdog Node** in a dual-architecture wildlife monitoring system. Its primary responsibility is to maintain an ultra-low-power standby profile while continuously observing the physical environment.

Upon detecting physical events, the Nano executes multi-sensor validation to eliminate thermal and environmental false positives. Once an event is confirmed as a true positive, the Nano latches a P-channel MOSFET power gate, booting the high-power media node (Raspberry Pi Zero W).

```
+-----------------------------------------------------------------------------------+
|                            EDGE TIER: WATCHDOG NODE                               |
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  |                         SENSOR SUITE (MODULAR)                              |  |
|  |  [PIR]   [IR Break Beam]   [RCWL-0516 Radar]   [BME280]   [Magnetic Switch] |  |
|  +-----+------------+-----------------+--------------+---------------+---------+  |
|        |            |                 |              |               |            |
|        v            v                 v              v               v            |
|  +-----------------------------------------------------------------------------+  |
|  |                     SENSOR ABSTRACTION LAYER (SAL)                          |  |
|  |           Unified ISensor Interface (Static Registry, Zero Heap)            |  |
|  +-------------------------------------+---------------------------------------+  |
|                                        |                                          |
|                                        v                                          |
|  +-----------------------------------------------------------------------------+  |
|  |                         SENSOR FUSION ENGINE                                |  |
|  |   Interrupt Wake -> Temporal Coincidence -> Thermal Comp -> Weighted Score  |  |
|  +-------------------------------------+---------------------------------------+  |
|                                        |                                          |
|                                        v                                          |
|  +-----------------------------------------------------------------------------+  |
|  |                 FINITE STATE MACHINE & POWER LIFECYCLE                      |  |
|  |         DEEP_SLEEP <---> FUSION_EVAL <---> PI_ACTIVE <---> COOLDOWN         |  |
|  +-------------------+-----------------------------------+---------------------+  |
|                      |                                   |                        |
|                      v (MOSFET Gate)                     v (Telemetry Handshake)  |
|             [Pi Zero W Power Rail]             [Pi Zero W UART / GPIO]            |
+-----------------------------------------------------------------------------------+
```

---

## 2.0 Hardware Constraints & Platform Engineering

### 2.1 ATmega328P Resource Budget

The classic Arduino Nano V3.0 features the ATmega328P microcontroller, which imposes strict hardware boundaries:

| Resource | Capacity | Firmware Allocation Budget | Safety Margin / Headroom |
| :--- | :--- | :--- | :--- |
| **Flash Memory** | 32 KB (30.5 KB with bootloader) | Max 14 KB (45%) | > 16 KB free |
| **SRAM** | 2048 Bytes (2 KB) | Max 600 Bytes static (29%) | > 1400 Bytes stack headroom |
| **EEPROM** | 1024 Bytes (1 KB) | 256 Bytes reserved for event ring | 768 Bytes free |
| **Operating Voltage** | 5.0 V | Regulated / Battery Divided | Level shifting required for 3.3V Pi |
| **Clock Speed** | 16 MHz (Crystal) | Prescaled to 8MHz/16MHz | Crystal active during run |

### 2.2 Low-Power Engineering on Nano V3.0 Clones

Standard commercial Nano V3.0 boards with CH340G USB bridges consume 15 mA to 25 mA even in software sleep due to auxiliary components:

1. **Power LED (PWR):** Draws ~3 mA to 5 mA continuously.
2. **AMS1117 5.0V Regulator:** Has a high quiescent current (~5 mA to 10 mA).
3. **CH340G USB-to-UART Chip:** Remains partially powered via VCC, drawing quiescent current.

#### Low-Power Hardware Mitigations

- **Physical Trace Cutting / LED Desoldering:** Remove the current-limiting resistor feeding the onboard power LED.
- **Direct Battery / Buck Supply:** Power the ATmega328P directly through the `5V` pin (or bypass the linear regulator using an ultra-low quiescent buck converter such as TI TPS62840, quiescent current $I_Q \approx 60\text{ nA}$).
- **Sleep Mode:** Use `SLEEP_MODE_PWR_DOWN` via `<avr/sleep.h>`, disabling the Analog Comparator, ADC (`ADCSRA = 0`), and Brown-out Detection during sleep (`sleep_bod_disable()`). This brings ATmega328P sleep current down to **$< 20\,\mu\text{A}$**.

---

## 3.0 Extensible Sensor Abstraction Layer (SAL)

To satisfy the requirement of dynamically adding or altering sensors without refactoring the core state machine, the firmware employs an object-oriented **Sensor Abstraction Layer (SAL)**.

### 3.1 Design Principles

- **Strict Zero-Heap Allocation:** No dynamic allocation (`new`, `malloc`, or `String`). All sensor instances, buffers, and registries are statically allocated at compile time.
- **Uniform Polymorphic Interface:** All sensor drivers implement a lightweight C++ interface `ISensor`.
- **Decoupled Acquisition & Evaluation:** Sensing logic is split into hardware polling, raw metric acquisition, and normalized confidence evaluation.

### 3.2 Unified Sensor Interface (`ISensor`)

```cpp
// Types of sensor data modalities
enum class SensorType : uint8_t {
    DIGITAL_INTERRUPT,  // Pin-change / external interrupt (PIR, Break Beam, Radar)
    DIGITAL_SWITCH,     // Contact switch (Magnetic reed switch)
    ANALOG_ADC,         // Analog voltage (Photodiode, Battery divider)
    I2C_BUS             // Multi-register environmental (BME280)
};

// Sensor health and readiness flags
enum class SensorStatus : uint8_t {
    UNINITIALIZED,
    READY,
    FAULT_OFFLINE,
    WARMING_UP
};

class ISensor {
public:
    virtual ~ISensor() = default;

    // Lifecycle
    virtual bool init() = 0;
    virtual void enterSleep() = 0;
    virtual void wake() = 0;

    // Acquisition & Evaluation
    virtual void poll() = 0;                            // Read physical lines/registers
    virtual bool isTriggered() const = 0;               // Boolean assertion
    virtual uint8_t getConfidence() const = 0;          // Normalized confidence: 0 - 100
    virtual int32_t getRawMetric() const = 0;           // Raw sensor value for telemetry

    // Metadata
    virtual SensorType getType() const = 0;
    virtual const char* getName() const = 0;
    virtual SensorStatus getStatus() const = 0;
};
```

### 3.3 Concrete Sensor Drivers

#### 1. Passive Infrared (PIR) Driver (`PirSensor`)

- **Modality:** Digital Interrupt (`SensorType::DIGITAL_INTERRUPT`).
- **Characteristics:** Broad volumetric field of view, sensitive to thermal radiation shifts.
- **Hardware Interface:** Configured to trigger an interrupt (`PCINT` or `INT0/INT1`) on pin change from LOW to HIGH.
- **Mitigations:** Thermal blindness at ambient temperatures near animal body temperature ($> 95^\circ\text{F} / 35^\circ\text{C}$).

#### 2. Infrared Break Beam Driver (`BreakBeamSensor`)

- **Modality:** Digital Interrupt (`SensorType::DIGITAL_INTERRUPT`).
- **Characteristics:** Active emitter-receiver pair. Output is active-low (beam break pulls line LOW).
- **Behavior:** Extremely fast response ($< 5\text{ ms}$), pinpoints exact spatial traversal (e.g., feeder entrance or perch).
- **Debounce:** Requires a 10 ms digital low-pass debounce to reject flying insects and wind-borne leaves.

#### 3. Microwave Doppler Radar Driver (`Rcwl0516Sensor`)

- **Modality:** Digital Interrupt (`SensorType::DIGITAL_INTERRUPT`).
- **Characteristics:** 3.18 GHz Doppler microwave radar. Output pin drives HIGH for ~2 seconds upon motion detection.
- **Advantage:** Penetrates plastic weather enclosures completely. Immune to ambient temperature blooms ($> 100^\circ\text{F}$), complementing the PIR.

#### 4. Magnetic Reed / Hall Switch Driver (`MagneticSwitchSensor`)

- **Modality:** Digital Switch (`SensorType::DIGITAL_SWITCH`).
- **Characteristics:** Detects mechanical movement (feeder lid opening or weighted perch hinge deflection).
- **Debounce:** Software edge debounce (20 ms refractory filter).

#### 5. BME280 Environmental Driver (`Bme280Sensor`)

- **Modality:** I2C Bus (`SensorType::I2C_BUS`, address `0x76` or `0x77`).
- **Characteristics:** Reads ambient temperature, relative humidity, and barometric pressure.
- **Role in Fusion:** Does not trigger motion directly; provides environmental context used by the fusion engine to dynamically adjust PIR and Radar confidence thresholds.

#### 6. Battery Voltage Monitor (`BatteryMonitorSensor`)

- **Modality:** Analog ADC (`SensorType::ANALOG_ADC`).
- **Hardware Interface:** Resistor divider (e.g., $100\,\text{k}\Omega / 27\,\text{k}\Omega$) connected to `A0`.
- **Reference:** Evaluated against the ATmega328P internal $1.1\,\text{V}$ stabilized bandgap reference (`INTERNAL`), avoiding inaccuracy caused by shifting battery rails.

### 3.4 Static Sensor Registry

To enable adding or swapping sensors without altering the state machine, sensors are held in a fixed-size static registry:

```cpp
constexpr uint8_t MAX_SENSORS = 6;

class SensorRegistry {
private:
    ISensor* sensors[MAX_SENSORS];
    uint8_t count = 0;

public:
    bool registerSensor(ISensor* sensor) {
        if (count >= MAX_SENSORS || sensor == nullptr) return false;
        sensors[count++] = sensor;
        return true;
    }

    void initAll() {
        for (uint8_t i = 0; i < count; ++i) sensors[i]->init();
    }

    void sleepAll() {
        for (uint8_t i = 0; i < count; ++i) sensors[i]->enterSleep();
    }

    void wakeAll() {
        for (uint8_t i = 0; i < count; ++i) sensors[i]->wake();
    }

    ISensor* get(uint8_t index) const {
        return (index < count) ? sensors[index] : nullptr;
    }

    uint8_t getCount() const { return count; }
};
```

---

## 4.0 Sensor Fusion & False-Positive Elimination Engine

Wildlife feeders deployed outdoors in direct sunlight face severe false-positive challenges:

1. **Thermal Blooms:** Ambient heat exceeding $100^\circ\text{F}$ reduces the IR contrast between animals and background, triggering false PIR pulses as heat waves shimmer.
2. **Vegetation Sway:** Tree branches moving in wind create optical and infrared noise.
3. **Insects / Raindrops:** Ephemeral interruption of optical beams.

### 4.1 Four-Stage Fusion Pipeline

```
[ WAKEUP INTERRUPT ] (PIR, Break Beam, or Radar fires interrupt)
        │
        ▼
[ STAGE 1: Fast Verification & Timestamping ]
        │ Record trigger source & start Coincidence Timer (T_coincidence)
        ▼
[ STAGE 2: Temporal Coincidence Window ]
        │ Monitor secondary sensors within T_window (e.g. 500ms - 1500ms)
        ▼
[ STAGE 3: Environmental Thermal Compensation ]
        │ Query BME280 temperature; shift weight between PIR and Radar
        ▼
[ STAGE 4: Weighted Confidence Aggregation ]
        │ Calculate Total Confidence: Score = Σ (w_i * Confidence_i)
        │
        ├─► Score >= Threshold (e.g., 75) ──► CONFIRMED TRIGGER -> Boot Pi
        │
        └─► Score <  Threshold            ──► FALSE POSITIVE -> Log & Sleep
```

### 4.2 Mathematical Scoring Model

The confidence score $C_{total}$ is evaluated as:

$$C_{total} = \sum_{i=1}^{N} \left( w_i(T_{env}) \cdot c_i \cdot \delta_i \right)$$

Where:

- $c_i \in [0, 100]$: Confidence score returned by sensor $i$.
- $\delta_i \in \{0, 1\}$: Binary state indicating whether sensor $i$ was active within the coincidence window $T_{window}$.
- $w_i(T_{env})$: Dynamic weight assigned to sensor $i$ based on ambient temperature $T_{env}$ from the BME280:

$$\sum w_i = 1.0$$

#### Dynamic Thermal Weight Shift

- **Standard Condition ($T_{ambient} < 85^\circ\text{F} / 29^\circ\text{C}$):**
  - $w_{PIR} = 0.40$
  - $w_{BreakBeam} = 0.40$
  - $w_{Radar} = 0.20$
- **High Heat Condition ($T_{ambient} \ge 95^\circ\text{F} / 35^\circ\text{C}$):**
  - $w_{PIR} = 0.15$ (attenuated due to thermal noise)
  - $w_{BreakBeam} = 0.45$ (unaffected by temperature)
  - $w_{Radar} = 0.40$ (Doppler microwave unaffected by ambient heat)

### 4.3 Rejection Matrix

| Trigger Combination | Coincidence Window ($\Delta t$) | Environmental Context | Fusion Result | Rationale |
| :--- | :--- | :--- | :--- | :--- |
| **PIR Only** | N/A (no secondary trigger) | Any | **REJECTED** | Likely tree shadow, heat gust, or distant movement outside feeder zone. |
| **Break Beam Only** | Pulse width $< 15\text{ ms}$ | Any | **REJECTED** | Bug or flying debris crossing beam path. |
| **PIR + Break Beam** | $\Delta t < 1200\text{ ms}$ | Normal ($< 90^\circ\text{F}$) | **CONFIRMED** | Animal approached area (PIR) and crossed feeder entry (Break Beam). |
| **Radar + Break Beam** | $\Delta t < 800\text{ ms}$ | High Heat ($> 95^\circ\text{F}$) | **CONFIRMED** | Radar confirms mass displacement while Break Beam confirms entry. |
| **Magnetic Switch Only** | Debounced $> 50\text{ ms}$ | Any | **CONFIRMED** | Physical tampering/opening of feeder lid or perch engagement. |

---

## 5.0 Inter-Processor Handshake & Telemetry: Trade-off Analysis & Recommendation

The communication interface between the Arduino Nano (Watchdog) and the Raspberry Pi Zero W (Media Node) must coordinate power gating and telemetry transfer.

### 5.1 Option A: Pure GPIO Pulse Handshake

In a pure GPIO handshake, communication is restricted to binary voltage states across dedicated pins:

```
[ Arduino Nano 5V ]                     [ Raspberry Pi Zero W 3.3V ]
  D8 (PWR_LATCH) ───[ Gate of P-MOSFET ]──► (Powers Pi 5V Rail)
  D7 (PI_STATUS) ◄───[ 1kΩ / 2kΩ Divider ]── GPIO 24 (Pi Booted / Heartbeat)
  D6 (SHUTDOWN_REQ) ◄─[ 1kΩ / 2kΩ Divider ]── GPIO 25 (Pi Shutdown Ready)
```

#### Protocol Flow

1. Nano triggers and asserts `PWR_LATCH` LOW to enable MOSFET.
2. Pi boots; Linux startup script sets GPIO 24 HIGH to announce readiness.
3. Pi executes camera capture and local transfer.
4. Pi sets GPIO 25 HIGH to request power cut, invokes `poweroff`, and Nano cuts power after a 10-second safety delay.

#### Advantages

- **Zero Software Complexity:** Uses standard digital I/O without serial drivers or packet parsers.
- **SRAM Footprint:** $< 10\text{ Bytes}$ of RAM consumed.
- **Immune to Baud Drift:** Independent of clock crystals or OS serial baud drift.

#### Disadvantages

- **Blind Wakeup:** The Pi receives no context regarding *why* it was woken (which sensor triggered, confidence score, battery level).
- **No Telemetry Transfer:** Sensor metrics, diagnostic counters, and battery status trapped on the Nano cannot be relayed to the Pi or forwarded to MQTT.

---

### 5.2 Option B: Hybrid GPIO Lifecycle + UART Serial Telemetry

This architecture decouples **hardware safety** from **data telemetry**:

- **Hardware Layer (GPIO):** Dedicated lines handle MOSFET latching and shutdown acknowledgement to prevent hangs.
- **Data Layer (UART Serial):** An asynchronous serial stream transfers structured sensor metrics and trigger metadata once the Pi is booted.

```
[ Arduino Nano 5V ]                                 [ Raspberry Pi Zero W 3.3V ]
  D8 (MOSFET_GATE) ─────[ P-MOSFET Gate ]──────────► (VCC 5V Supply to Pi)
  D7 (SHUTDOWN_ACK) ◄───[ Direct 3.3V to 5V In ]───── GPIO 25 (Pi Poweroff ACK)
  TX (D1, 5V)       ───►[ 1kΩ / 2kΩ Divider ]───────► RX (GPIO 15, 3.3V)
  RX (D0, 5V)       ◄───[ Direct 3.3V to 5V In ]───── TX (GPIO 14, 3.3V)
```

#### Protocol Flow

1. **Power Up:** Nano latches MOSFET on.
2. **OS Boot:** Pi boots Linux (~15-20 sec). A lightweight daemon (`watchdog-bridge.py`) starts and queries the Nano via UART (`GET_TELEMETRY`).
3. **Telemetry Push:** Nano responds with a compact binary or JSON packet containing:
   - Trigger sensor ID and confidence score.
   - Delta time between sensors.
   - Ambient temperature/humidity from BME280.
   - Pre-boot and loaded battery voltage.
   - Running counter of false positives rejected since last boot.
4. **Pi Ingestion:** The Pi packages the video payload *and* the Nano telemetry into a single MQTT payload published to `telemetry/feeder-1` (matching [Logical_Block_Diagram.md](file:///Users/davidkester/Workspace/SquirrelFeeder/Design_Docs/Logical_Block_Diagram.md)).
5. **Failsafe Shutdown:** Pi initiates OS halt, asserts `SHUTDOWN_ACK`, and Nano de-energizes the MOSFET.

---

### 5.3 Comparison Matrix

| Criteria | Option A: Pure GPIO Pulse | Option B: Hybrid GPIO + UART |
| :--- | :--- | :--- |
| **SRAM Overhead** | Negligible (~8 bytes) | Minimal (~64 bytes serial RX/TX buffer) |
| **Flash Overhead** | ~200 bytes | ~1.8 KB (Serial + packet serialization) |
| **Telemetry Capability** | None (Blind trigger) | **Full telemetry & sensor metrics export** |
| **Observability** | No health visibility | Remote dashboard sees battery, temp, sensor stats |
| **Failsafe Resilience** | High | **High** (GPIO watchdog acts independently of UART) |
| **Level Shifter Complexity** | Requires 2 passive dividers | Requires 1 passive divider (Nano TX -> Pi RX) |

---

### 5.4 Recommendation & Engineering Rationale

> [!IMPORTANT]
> **Recommendation:** Adopt **Option B: Hybrid GPIO Lifecycle + UART Serial Telemetry**.

#### Rationale

1. **Meets Future Metrics Requirement:** The user specification explicitly mandates capturing sensor metrics. Pure GPIO cannot convey sensor health, battery voltage under load, or false-positive counts.
2. **Hardware Failsafe Independence:** By assigning MOSFET power cut and hard timeout to the Nano's internal timer and a dedicated GPIO shutdown ACK line, the system is 100% protected against Pi software lockups or serial corruption. If UART hangs, the hardware timer cuts power after a hard ceiling (e.g., 90 seconds).
3. **Zero Active Cost:** The UART hardware on both chips is idle while sleeping. Serial transmission only occurs during the active video recording window when the Pi is already powered.

### 5.5 Electrical Level Shifting Schematic

The Raspberry Pi Zero W GPIO pins are **not 5V tolerant**. Connecting a 5V Nano TX pin directly to a Pi RX pin will destroy the Pi SoC.

```
Nano Pin TX (5V Logic) 
          │
         [1 kΩ Resistor]
          │
          ├───► To Pi Zero W Pin 10 (GPIO 15 / RXD) [3.3V Logic Safe]
          │
         [2 kΩ Resistor]
          │
         GND

Pi Pin 8 (GPIO 14 / TXD, 3.3V) ────► To Nano Pin RX (D0, 5V Logic)
(Direct connection safe: ATmega328P VIH min is 0.6 * VCC = 3.0V; 3.3V satisfies HIGH)
```

---

## 6.0 Sensor Metrics & Telemetry Framework

To support future metric analysis in the Centralized Data Lakehouse, the Nano maintains an in-memory telemetry model updated during each sensing and power cycle.

### 6.1 Telemetry Data Model

```cpp
struct __attribute__((packed)) EventTelemetry {
    uint32_t bootCount;          // Monotonically increasing wake counter
    uint8_t  triggerSource;      // Bitmask: [0: PIR, 1: BreakBeam, 2: Radar, 3: Mag]
    uint8_t  confidenceScore;    // Evaluated fusion confidence (0-100)
    uint16_t coincidenceTimeMs;  // Temporal delta between 1st and 2nd sensor triggers
    int16_t  ambientTempC_x10;   // Ambient temperature (°C * 10, e.g. 325 = 32.5°C)
    uint16_t ambientHumidity_x10;// Relative humidity (% * 10)
    uint16_t vbatRestingMv;      // Battery voltage before Pi boot (mV)
    uint16_t vbatLoadedMv;       // Battery voltage under Pi boot load (mV)
    uint16_t falsePositivesFiltered; // False positives rejected since last Pi boot
    uint16_t fusionLatencyMs;    // Time spent in fusion evaluation stage
};
```

*Total struct size: exactly **20 bytes**.*

### 6.2 Packet Formatting for UART Transmission

The telemetry packet can be transmitted as either a compact binary framing or compact newline-delimited JSON. Given the Pi's processing power, **compact JSON** allows easier schema validation on the Pi:

```json
{"boot":142,"trig":3,"conf":88,"dt_ms":420,"temp":33.4,"hum":58.2,"v_rest":4120,"v_load":3840,"fp_rej":14,"lat_ms":62}
```

---

## 7.0 Finite State Machine (FSM) & Power Lifecycle

The firmware is structured as a non-blocking deterministic Finite State Machine (FSM).

### 7.1 State Transition Diagram

```
       ┌────────────────────────────────────────────────────────┐
       │                                                        │
       ▼                                                        │
+──────────────+    Interrupt (Pin Change)    +-----------------+--+
|  DEEP_SLEEP  | ───────────────────────────► |   FUSION_EVAL      |
+──────────────+                              +-----------------+--+
       ▲                                                │
       │ Coincidence Timeout / Low Confidence           │ Confirmed Trigger
       │ (False Positive Rejection)                     │ (Score >= 75)
       └────────────────────────────────────────────────┼──────────┐
                                                        │          │
                                                        ▼          │
+-------------------+     Pi Shutdown ACK     +-----------------+  │
| COOLDOWN_REFRACT  | ◄────────────────────── | PI_ACTIVE_MON   |  │
+-------------------+                         +-----------------+  │
       │                                                ▲          │
       │ Refractory Period Elapsed (e.g., 30s)          │          │
       └────────────────────────────────────────────────┴──────────┘
                                              Pi Latched & Telemetry Sent
```

### 7.2 State Specifications

#### 1. `STATE_DEEP_SLEEP`

- **CPU:** AVR `SLEEP_MODE_PWR_DOWN`.
- **Peripherals:** ADC disabled, Watchdog timer enabled (8-second periodic wake for battery check).
- **Interrupts:** Pin Change Interrupts (`PCINT`) armed on PIR, Break Beam, and Radar pins.
- **Power:** $< 20\,\mu\text{A}$.

#### 2. `STATE_FUSION_EVAL`

- **Trigger:** Pin Change Interrupt fires.
- **Action:** Wake CPU, read millis counter, capture primary sensor trigger. Start coincidence window timer ($T_{window} = 1200\text{ ms}$).
- **Evaluation:** Poll secondary sensors. Query BME280 temperature to calculate weighted confidence.
- **Outcome:** If confidence $\ge 75$, transition to `STATE_PI_ACTIVE_MON`; otherwise increment `falsePositivesFiltered` and return to `STATE_DEEP_SLEEP`.

#### 3. `STATE_PI_ACTIVE_MON`

- **Action:** Assert MOSFET gate LOW (powering the Raspberry Pi Zero W). Start safety failsafe timer ($T_{failsafe} = 90\text{ sec}$).
- **Communication:** Measure loaded battery voltage (`vbatLoadedMv`). Listen on UART for Pi telemetry request and transmit JSON packet.
- **Linger Window:** As per Functional Requirement 3.4, the Pi may request a linger window (3 to 5 minutes) for live dashboard streaming. The Nano adjusts its safety timer to match the commanded linger timeout.

#### 4. `STATE_COOLDOWN_REFRACT`

- **Trigger:** Pi asserts `SHUTDOWN_ACK` (or safety timeout expires).
- **Action:** De-assert MOSFET gate (cutting Pi power completely).
- **Refractory Window:** Enter low-power sleep for a 30-second refractory window where motion interrupts are masked, preventing immediate re-triggering while the animal is finishing feeding.
- **Transition:** Return to `STATE_DEEP_SLEEP`.

---

## 8.0 Memory Budget & Resource Allocation

### 8.1 SRAM Allocation Breakdown (2048 Bytes Total)

```
+-------------------------------------------------------------+
| Memory Section            | Allocated Size | % of Total RAM |
+---------------------------+----------------+----------------+
| Hardware Serial Buffers   | 64 Bytes       | 3.1 %          |
| Sensor Registry (6 ptrs)  | 12 Bytes       | 0.6 %          |
| Concrete Sensor Objects   | 84 Bytes       | 4.1 %          |
| Fusion Engine State       | 32 Bytes       | 1.6 %          |
| Telemetry Active Buffer   | 20 Bytes       | 1.0 %          |
| FSM & System Timers       | 28 Bytes       | 1.4 %          |
| C++ Runtime & Misc Globals| 60 Bytes       | 2.9 %          |
+---------------------------+----------------+----------------+
| TOTAL STATIC ALLOCATION   | ~300 Bytes     | 14.6 %         |
| DYNAMIC STACK HEADROOM    | ~1748 Bytes    | 85.4 %         |
+-------------------------------------------------------------+
```

### 8.2 Arduino Nano V3.0 Pinout Plan

| Nano Pin | Physical Port | Function | Direction | Connected Device | Voltage Logic |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **D0** | PD0 | `RXD` (UART Receive) | Input | Pi Zero W TXD (GPIO 14) | 3.3V into 5V (Direct) |
| **D1** | PD1 | `TXD` (UART Transmit) | Output | Pi Zero W RXD (GPIO 15) | 5V via 1k/2k Divider |
| **D2** | PD2 | `INT0` (PIR Interrupt) | Input | PIR Motion Sensor Out | 3.3V / 5V Logic |
| **D3** | PD3 | `INT1` (Break Beam Int) | Input | IR Break Beam Receiver | Open-collector w/ pullup |
| **D4** | PD4 | `PCINT20` (Radar In) | Input | RCWL-0516 Doppler Out | 3.3V Logic |
| **D5** | PD5 | `PCINT21` (Mag Switch) | Input | Magnetic Reed Switch | Pull-up to 5V |
| **D6** | PD6 | `SHUTDOWN_ACK` | Input | Pi Shutdown Signal (GPIO 25) | 3.3V into 5V (Direct) |
| **D7** | PD7 | `PI_STATUS_PULSE` | Input | Pi Heartbeat Pin (GPIO 24) | 3.3V into 5V (Direct) |
| **D8** | PB0 | `MOSFET_GATE_CTRL` | Output | P-MOSFET Gate Driver (Active LOW) | 5V Output (via Gate BJT) |
| **A0** | PC0 | `ADC0` (Battery Sense) | Analog In | Battery Divider ($100\text{k}\Omega/27\text{k}\Omega$) | Up to 1.1V (Bandgap Ref) |
| **A4** | PC4 | `SDA` (I2C Data) | Bi-directional | BME280 Environmental Sensor | 3.3V I2C (Pull-ups to 3.3V) |
| **A5** | PC5 | `SCL` (I2C Clock) | Output | BME280 Environmental Sensor | 3.3V I2C (Pull-ups to 3.3V) |

---

## 9.0 Verification & Implementation Roadmap

### 9.1 Verification Phases

1. **Module 1: Low-Power Baseline Test**
   - Measure quiescent current of modified Nano in `SLEEP_MODE_PWR_DOWN` with power LED trace cut. Verify current is $< 50\,\mu\text{A}$.
2. **Module 2: SAL & Driver Extensibility Test**
   - Unit test mock sensors against the `ISensor` interface. Verify static registry initialization and zero dynamic allocation (`malloc` assertion).
3. **Module 3: Fusion Coincidence & Thermal Rejection Validation**
   - Inject simulated single-sensor pulses (PIR only, Break Beam only) and verify rejection.
   - Inject coupled pulses within $T_{window} = 800\text{ ms}$ and verify state transition to `STATE_PI_ACTIVE_MON`.
4. **Module 4: Level Shifter & Handshake Electrical Validation**
   - Probe Nano TX line across resistor divider with an oscilloscope to confirm voltage ceiling does not exceed $3.3\,\text{V}$.
   - Verify Pi Zero W cold boot sequence and graceful shutdown GPIO pulse trigger.
5. **Module 5: Telemetry Stream Integration**
   - Verify UART JSON string decoding in Python on the Pi Zero W and validate MQTT message format against the backend broker.
