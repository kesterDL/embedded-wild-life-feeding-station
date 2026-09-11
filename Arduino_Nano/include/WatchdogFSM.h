#ifndef WATCHDOG_FSM_H
#define WATCHDOG_FSM_H

#include <cstdint>

#ifdef UNIT_TEST
#include "ArduinoMock.h"
#else
#include <Arduino.h>
#include <avr/sleep.h>
#include <avr/power.h>
#include <avr/interrupt.h>
#endif

// Hardware Pin Definitions (Nano V3.0)
constexpr uint8_t PIN_PIR_INTERRUPT = 2;  // INT0 on ATmega328P (Active HIGH)
constexpr uint8_t PIN_SHUTDOWN_ACK  = 6;  // Input from Pi Zero W GPIO 25 (Active HIGH)
constexpr uint8_t PIN_MOSFET_GATE   = 8;  // Output to P-MOSFET driver (Active LOW = ON, HIGH = OFF)
constexpr uint8_t PIN_STATUS_LED    = 13; // Onboard LED for status indication

// Hardware Timers & Timeouts
constexpr unsigned long FAILSAFE_TIMEOUT_MS = 60000UL; // 60s max active runtime failsafe
constexpr unsigned long SHUTDOWN_DELAY_MS   = 5000UL;  // 5s grace period for OS halt after ACK

enum class WatchdogState : uint8_t {
    STATE_SLEEP = 0,
    STATE_POWER_ON,
    STATE_WAIT_SHUTDOWN,
    STATE_POWER_OFF_DELAY
};

class WatchdogFSM {
public:
    WatchdogFSM();

    // Lifecycle
    void init();
    void update();
    void onMotionDetected();

    // Power & Sleep Control
    void enterDeepSleep();
    void cutPower();
    void applyPower();

    // State Inspection
    WatchdogState getState() const { return m_state; }
    unsigned long getActiveDuration() const;

private:
    WatchdogState m_state;
    unsigned long m_powerOnTime;
    unsigned long m_ackReceivedTime;
};

#endif // WATCHDOG_FSM_H
