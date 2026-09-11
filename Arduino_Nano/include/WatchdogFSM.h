#ifndef WATCHDOG_FSM_H
#define WATCHDOG_FSM_H

#include <cstdint>

#ifdef UNIT_TEST
#include "ArduinoMock.h"
#else
#include <Arduino.h>
#include <avr/sleep.h>
#include <avr/power.h>
#endif

// Pin Definitions according to System Design
constexpr uint8_t PIN_PIR_INTERRUPT = 2;  // INT0 on ATmega328P
constexpr uint8_t PIN_SHUTDOWN_ACK  = 6;  // Input from Pi Zero W GPIO 25
constexpr uint8_t PIN_MOSFET_GATE   = 8;  // Active LOW enables P-MOSFET
constexpr uint8_t PIN_STATUS_LED    = 13; // Onboard activity LED

// Timing Constraints
constexpr unsigned long FAILSAFE_TIMEOUT_MS = 60000UL; // 60s max active window
constexpr unsigned long SHUTDOWN_DELAY_MS   = 5000UL;  // 5s settling delay after ACK

enum class WatchdogState : uint8_t {
    STATE_SLEEP = 0,
    STATE_POWER_ON,
    STATE_WAIT_SHUTDOWN,
    STATE_POWER_OFF_DELAY
};

class WatchdogFSM {
public:
    WatchdogFSM();

    void init();
    void update();
    void onMotionDetected();

    WatchdogState getState() const { return m_state; }
    unsigned long getActiveTime() const { return m_activeTime; }

private:
    WatchdogState m_state;
    unsigned long m_activeTime;
};

#endif // WATCHDOG_FSM_H
