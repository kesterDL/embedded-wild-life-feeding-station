#include "../include/WatchdogFSM.h"

WatchdogFSM::WatchdogFSM() 
    : m_state(WatchdogState::STATE_SLEEP),
      m_powerOnTime(0),
      m_ackReceivedTime(0) {}

void WatchdogFSM::init() {
    // Configure power-switching gate: Output, default HIGH (Power OFF)
    pinMode(PIN_MOSFET_GATE, OUTPUT);
    digitalWrite(PIN_MOSFET_GATE, HIGH);

    // Status LED
    pinMode(PIN_STATUS_LED, OUTPUT);
    digitalWrite(PIN_STATUS_LED, LOW);

    // Sensor & Signaling Inputs
    pinMode(PIN_PIR_INTERRUPT, INPUT);
    pinMode(PIN_SHUTDOWN_ACK, INPUT);

    m_state = WatchdogState::STATE_SLEEP;
    m_powerOnTime = 0;
    m_ackReceivedTime = 0;
}

void WatchdogFSM::applyPower() {
    // Assert LOW to saturate P-MOSFET gate (powers 5V rail to Pi Zero W)
    digitalWrite(PIN_MOSFET_GATE, LOW);
    digitalWrite(PIN_STATUS_LED, HIGH);
}

void WatchdogFSM::cutPower() {
    // Release HIGH to cut off P-MOSFET gate
    digitalWrite(PIN_MOSFET_GATE, HIGH);
    digitalWrite(PIN_STATUS_LED, LOW);
}

void WatchdogFSM::enterDeepSleep() {
#ifndef UNIT_TEST
    // Disable ADC to conserve ~200 uA
    ADCSRA = 0;

    // Set deep sleep mode
    set_sleep_mode(SLEEP_MODE_PWR_DOWN);
    sleep_enable();

    // Disable Brown-Out Detector during sleep (saving ~25 uA)
    sleep_bod_disable();

    // Re-enable interrupts before entering sleep
    sei();

    // Halt CPU until external INT0 trigger
    sleep_cpu();

    // Execution resumes here after interrupt
    sleep_disable();
#else
    sleep_enable();
    sleep_bod_disable();
    sleep_cpu();
    sleep_disable();
#endif
}

void WatchdogFSM::onMotionDetected() {
    if (m_state == WatchdogState::STATE_SLEEP) {
        m_state = WatchdogState::STATE_POWER_ON;
    }
}

unsigned long WatchdogFSM::getActiveDuration() const {
    if (m_state == WatchdogState::STATE_SLEEP || m_powerOnTime == 0) {
        return 0;
    }
    return millis() - m_powerOnTime;
}

void WatchdogFSM::update() {
    switch (m_state) {
        case WatchdogState::STATE_SLEEP:
            // Remain in deep sleep until woken by interrupt
            enterDeepSleep();
            break;

        case WatchdogState::STATE_POWER_ON:
            applyPower();
            m_powerOnTime = millis();
            m_state = WatchdogState::STATE_WAIT_SHUTDOWN;
            break;

        case WatchdogState::STATE_WAIT_SHUTDOWN:
            // Check for graceful shutdown acknowledgment from Pi Zero W
            if (digitalRead(PIN_SHUTDOWN_ACK) == HIGH) {
                m_ackReceivedTime = millis();
                m_state = WatchdogState::STATE_POWER_OFF_DELAY;
            } 
            // Enforce hardware failsafe timeout to prevent battery drain on hung OS
            else if ((millis() - m_powerOnTime) >= FAILSAFE_TIMEOUT_MS) {
                cutPower();
                m_state = WatchdogState::STATE_SLEEP;
            }
            break;

        case WatchdogState::STATE_POWER_OFF_DELAY:
            // Allow Linux kernel adequate grace period (5s) to complete disk unmount and halt
            if ((millis() - m_ackReceivedTime) >= SHUTDOWN_DELAY_MS) {
                cutPower();
                m_state = WatchdogState::STATE_SLEEP;
            }
            break;
    }
}
