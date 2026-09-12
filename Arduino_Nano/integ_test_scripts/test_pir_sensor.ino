/*
 * Standalone PIR Sensor Hardware Integration Test Firmware
 * Target: Arduino Nano V3.0 (ATmega328P)
 *
 * Purpose:
 *   Validates physical HC-SR501 PIR motion sensor in isolation:
 *   1. Measures sensor warm-up & stabilization period (~30-60s)
 *   2. Verifies Pin D2 (INT0) external hardware interrupt triggering on RISING edge
 *   3. Verifies Pin D2 digital state changes (HIGH on motion, LOW on idle)
 *   4. Measures trigger pulse duration (HIGH time determined by time pot)
 *   5. Keeps P-MOSFET gate (Pin D8) HIGH (Power OFF) to keep Raspberry Pi safely isolated
 *   6. Mirrors sensor state to onboard LED (Pin D13) for instant visual feedback
 *   7. Provides structured serial telemetry (115200 baud) for automated host test runner
 *
 * Hardware Connections:
 *   - HC-SR501 VCC  -> Arduino Nano 5V Pin
 *   - HC-SR501 GND  -> Arduino Nano GND Pin
 *   - HC-SR501 OUT  -> Arduino Nano Pin D2 (INT0)
 *   - Arduino D13   -> Built-in Status LED (Visual indicator)
 *   - Arduino D8    -> MOSFET Gate (Held HIGH to cut power to Pi during test)
 *
 * Sensor Settings:
 *   - Trigger Mode Jumper: Set to 'H' (Repeatable Trigger)
 *   - Time Delay Potentiometer: Turn fully counter-clockwise (~3s shortest pulse)
 *   - Sensitivity Potentiometer: Adjust as needed (middle position recommended)
 */

#include <Arduino.h>

// Hardware Pin Definitions
constexpr uint8_t PIN_PIR_INTERRUPT = 2;   // INT0 on ATmega328P (HC-SR501 OUT)
constexpr uint8_t PIN_SHUTDOWN_ACK  = 6;   // Unused in isolated test (Input)
constexpr uint8_t PIN_MOSFET_GATE   = 8;   // Held HIGH to isolate Pi (Active LOW = ON)
constexpr uint8_t PIN_STATUS_LED    = 13;  // Onboard LED indicator

// Timing & Configuration
constexpr unsigned long SERIAL_BAUD_RATE    = 115200;
constexpr unsigned long WARMUP_DURATION_MS  = 30000UL; // 30s HC-SR501 stabilization period
constexpr unsigned long HEARTBEAT_INTERVAL_MS = 10000UL;

enum class TestState : uint8_t {
    WARMING_UP,
    READY_MONITORING
};

// Global State Variables
TestState currentState = TestState::WARMING_UP;
unsigned long warmupStartTime = 0;
unsigned long lastWarmupReportTime = 0;
unsigned long lastHeartbeatTime = 0;

// Motion Tracking Variables
int lastPinState = LOW;
unsigned long motionStartTime = 0;
unsigned long motionDuration = 0;
unsigned long totalTriggers = 0;

// Interrupt Tracking (Volatile for ISR safety)
volatile unsigned long isrTriggerCount = 0;
volatile unsigned long isrLastTime = 0;
volatile bool isrEventPending = false;

// Hardware Interrupt Service Routine for Pin D2 (INT0)
void isrPirMotion() {
    isrTriggerCount++;
    isrLastTime = millis();
    isrEventPending = true;
}

void printHelp() {
    Serial.println(F("--- Available Serial Commands ---"));
    Serial.println(F("  PING     - Check connection with Nano"));
    Serial.println(F("  STATUS   - Output current sensor pin state & trigger counts"));
    Serial.println(F("  SKIP     - Bypass remaining warm-up time immediately"));
    Serial.println(F("  WARMUP   - Restart 30s sensor warm-up countdown"));
    Serial.println(F("  RESET    - Reset trigger counts and timer metrics"));
    Serial.println(F("  HELP     - Print this command menu"));
    Serial.println(F("---------------------------------"));
}

void printStatus() {
    int currentPin = digitalRead(PIN_PIR_INTERRUPT);
    Serial.print(F("[STATUS] State: "));
    Serial.print(currentState == TestState::WARMING_UP ? F("WARMING_UP") : F("READY"));
    Serial.print(F(" | Pin D2: "));
    Serial.print(currentPin == HIGH ? F("HIGH (Motion)") : F("LOW (Idle)"));
    Serial.print(F(" | Triggers: "));
    Serial.print(totalTriggers);
    Serial.print(F(" | ISR Count: "));
    Serial.print(isrTriggerCount);
    Serial.print(F(" | Uptime: "));
    Serial.print(millis() / 1000);
    Serial.println(F("s"));
}

void processSerialCommand(const String& cmd) {
    String cleanCmd = cmd;
    cleanCmd.trim();
    cleanCmd.toUpperCase();

    if (cleanCmd == "PING") {
        Serial.println(F("[PONG] Arduino Nano PIR Test Firmware Online"));
    } else if (cleanCmd == "STATUS") {
        printStatus();
    } else if (cleanCmd == "SKIP") {
        if (currentState == TestState::WARMING_UP) {
            currentState = TestState::READY_MONITORING;
            digitalWrite(PIN_STATUS_LED, LOW);
            Serial.println(F("[WARMUP_SKIPPED] Warm-up bypassed by operator. Sensor monitoring active."));
            Serial.println(F("[READY] Sensor monitoring active. Wave hand across PIR sensor to test."));
        } else {
            Serial.println(F("[INFO] Sensor already in active monitoring state."));
        }
    } else if (cleanCmd == "WARMUP") {
        currentState = TestState::WARMING_UP;
        warmupStartTime = millis();
        lastWarmupReportTime = 0;
        Serial.println(F("[WARMUP_RESTART] Sensor warm-up countdown restarted (30 seconds)."));
    } else if (cleanCmd == "RESET") {
        totalTriggers = 0;
        noInterrupts();
        isrTriggerCount = 0;
        isrEventPending = false;
        interrupts();
        Serial.println(F("[RESET] Trigger counters and metrics reset to 0."));
    } else if (cleanCmd == "HELP" || cleanCmd == "?") {
        printHelp();
    } else if (cleanCmd.length() > 0) {
        Serial.print(F("[UNKNOWN_CMD] Unrecognized command: '"));
        Serial.print(cleanCmd);
        Serial.println(F("'. Send 'HELP' for valid commands."));
    }
}

void setup() {
    // 1. Initialize Serial Communication
    Serial.begin(SERIAL_BAUD_RATE);
    while (!Serial && millis() < 2000) {
        // Wait up to 2 seconds for USB serial connection on Leonardo/Micro/Nano
    }

    // 2. Configure Hardware Pins
    pinMode(PIN_PIR_INTERRUPT, INPUT);
    pinMode(PIN_SHUTDOWN_ACK, INPUT);
    pinMode(PIN_STATUS_LED, OUTPUT);
    digitalWrite(PIN_STATUS_LED, LOW);

    // Ensure Raspberry Pi remains safely unpowered during isolated PIR testing
    pinMode(PIN_MOSFET_GATE, OUTPUT);
    digitalWrite(PIN_MOSFET_GATE, HIGH); // Active-LOW: HIGH = Cut Power

    // 3. Attach Hardware Interrupt on Pin D2 (INT0)
    attachInterrupt(digitalPinToInterrupt(PIN_PIR_INTERRUPT), isrPirMotion, RISING);

    // 4. Initialize Warm-up State
    currentState = TestState::WARMING_UP;
    warmupStartTime = millis();
    lastWarmupReportTime = millis();
    lastHeartbeatTime = millis();
    lastPinState = digitalRead(PIN_PIR_INTERRUPT);

    // 5. Emit Boot Telemetry Banner
    Serial.println();
    Serial.println(F("============================================================"));
    Serial.println(F("     Arduino Nano - HC-SR501 PIR Hardware Integration Test  "));
    Serial.println(F("============================================================"));
    Serial.print(F("Pin D2 (INT0):    PIR Sensor OUT (Input)\n"));
    Serial.print(F("Pin D13:          Status LED (Output)\n"));
    Serial.print(F("Pin D8:           MOSFET Gate (HIGH / Pi Power Isolated)\n"));
    Serial.print(F("Warm-up Period:   30 seconds\n"));
    Serial.print(F("Baud Rate:        115200\n"));
    Serial.println(F("============================================================"));
    Serial.println(F("[INIT] Initialized successfully. Starting sensor stabilization..."));
    printHelp();
}

void loop() {
    unsigned long now = millis();

    // 1. Check for Incoming Serial Commands
    if (Serial.available() > 0) {
        String input = Serial.readStringUntil('\n');
        processSerialCommand(input);
    }

    // 2. Handle State Logic
    if (currentState == TestState::WARMING_UP) {
        unsigned long elapsed = now - warmupStartTime;

        // Visual indication during warm-up: Blink onboard LED at 2 Hz
        digitalWrite(PIN_STATUS_LED, (elapsed / 250) % 2 == 0 ? HIGH : LOW);

        // Emit countdown update every 5 seconds
        if (now - lastWarmupReportTime >= 5000UL || lastWarmupReportTime == 0) {
            lastWarmupReportTime = now;
            long remaining = (long)(WARMUP_DURATION_MS - elapsed) / 1000;
            if (remaining > 0) {
                Serial.print(F("[WARMUP] Stabilizing HC-SR501 pyroelectric sensor... "));
                Serial.print(remaining);
                Serial.println(F("s remaining (Send 'SKIP' to bypass)"));
            }
        }

        // Check if warm-up completed
        if (elapsed >= WARMUP_DURATION_MS) {
            currentState = TestState::READY_MONITORING;
            digitalWrite(PIN_STATUS_LED, LOW);
            lastPinState = digitalRead(PIN_PIR_INTERRUPT);

            Serial.println(F("------------------------------------------------------------"));
            Serial.println(F("[READY] Sensor warm-up complete! Physical sensor stabilized."));
            Serial.println(F("[READY] Monitoring for motion triggers on Pin D2..."));
            Serial.println(F("[PROMPT] Wave your hand in front of the HC-SR501 lens."));
            Serial.println(F("------------------------------------------------------------"));
        }
        return;
    }

    // 3. Active Monitoring State
    int currentPinState = digitalRead(PIN_PIR_INTERRUPT);

    // Process Pending Interrupt Flag
    if (isrEventPending) {
        noInterrupts();
        isrEventPending = false;
        unsigned long isrTime = isrLastTime;
        unsigned long count = isrTriggerCount;
        interrupts();

        Serial.print(F("[ISR_EVENT] Hardware interrupt INT0 fired on RISING edge! Total ISR events: "));
        Serial.print(count);
        Serial.print(F(" at "));
        Serial.print(isrTime);
        Serial.println(F(" ms"));
    }

    // Detect Transition: LOW -> HIGH (Motion Trigger Detected)
    if (lastPinState == LOW && currentPinState == HIGH) {
        totalTriggers++;
        motionStartTime = now;
        digitalWrite(PIN_STATUS_LED, HIGH); // Turn ON LED for visual feedback

        Serial.println();
        Serial.println(F(">>> [MOTION_DETECTED] <<<"));
        Serial.print(F("[TRIGGER] Trigger #"));
        Serial.print(totalTriggers);
        Serial.print(F(" | Pin D2: HIGH"));
        Serial.print(F(" | Timestamp: "));
        Serial.print(now);
        Serial.println(F(" ms"));
        Serial.println(F("[STATUS_LED] Onboard LED (Pin 13) turned ON."));
    }
    // Detect Transition: HIGH -> LOW (Motion Ended / Sensor Reset)
    else if (lastPinState == HIGH && currentPinState == LOW) {
        motionDuration = now - motionStartTime;
        digitalWrite(PIN_STATUS_LED, LOW); // Turn OFF LED

        Serial.println();
        Serial.println(F("<<< [MOTION_CLEARED] <<<"));
        Serial.print(F("[CLEAR] Motion pulse ended | Pin D2: LOW"));
        Serial.print(F(" | Pulse Duration: "));
        Serial.print(motionDuration);
        Serial.println(F(" ms"));
        Serial.println(F("[STATUS_LED] Onboard LED (Pin 13) turned OFF."));
        Serial.println(F("[READY] Sensor reset. Ready for next motion trigger."));
    }

    lastPinState = currentPinState;

    // Emit periodic idle heartbeat every 10 seconds if no transitions occur
    if (now - lastHeartbeatTime >= HEARTBEAT_INTERVAL_MS) {
        lastHeartbeatTime = now;
        if (currentPinState == LOW) {
            Serial.print(F("[IDLE_OK] Quiescent state verified: Pin D2 is LOW (no false motion). Uptime: "));
            Serial.print(now / 1000);
            Serial.print(F("s | Triggers: "));
            Serial.println(totalTriggers);
        } else {
            unsigned long activeElapsed = now - motionStartTime;
            Serial.print(F("[ACTIVE_HOLD] Pin D2 currently HIGH (Motion ongoing). Active for: "));
            Serial.print(activeElapsed);
            Serial.println(F(" ms"));
        }
    }

    delay(20); // 20ms polling interval for responsive debounce
}
