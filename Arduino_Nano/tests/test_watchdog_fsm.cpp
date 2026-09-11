#include <cassert>
#include <iostream>
#include "ArduinoMock.h"
#include "WatchdogFSM.h"

void run_test(const char* testName, bool condition) {
    if (condition) {
        std::cout << "  [PASS] " << testName << std::endl;
    } else {
        std::cerr << "  [FAIL] " << testName << std::endl;
        assert(false && "Test failed!");
    }
}

void test_initial_pin_configuration() {
    MockArduinoPlatform::instance().reset();
    WatchdogFSM fsm;
    fsm.init();

    // D8 (MOSFET) must be OUTPUT and default HIGH (Active-LOW cut off)
    run_test("D8 configured as OUTPUT", MockArduinoPlatform::instance().getPinMode(PIN_MOSFET_GATE) == OUTPUT);
    run_test("D8 initial state is HIGH (Power OFF)", MockArduinoPlatform::instance().getPinValue(PIN_MOSFET_GATE) == HIGH);

    // D2 (PIR) must be INPUT
    run_test("D2 configured as INPUT", MockArduinoPlatform::instance().getPinMode(PIN_PIR_INTERRUPT) == INPUT);

    // D6 (Shutdown ACK) must be INPUT
    run_test("D6 configured as INPUT", MockArduinoPlatform::instance().getPinMode(PIN_SHUTDOWN_ACK) == INPUT);

    // Initial state is SLEEP
    run_test("Initial state is STATE_SLEEP", fsm.getState() == WatchdogState::STATE_SLEEP);
}

void test_motion_detection_triggers_power_on() {
    MockArduinoPlatform::instance().reset();
    WatchdogFSM fsm;
    fsm.init();

    // Trigger PIR interrupt
    fsm.onMotionDetected();
    run_test("State transitions to STATE_POWER_ON upon motion", fsm.getState() == WatchdogState::STATE_POWER_ON);

    // FSM update cycle
    fsm.update();
    run_test("D8 asserted LOW (Power ON to Pi)", MockArduinoPlatform::instance().getPinValue(PIN_MOSFET_GATE) == LOW);
    run_test("State advances to STATE_WAIT_SHUTDOWN", fsm.getState() == WatchdogState::STATE_WAIT_SHUTDOWN);
}

void test_shutdown_ack_and_clean_poweroff() {
    MockArduinoPlatform::instance().reset();
    WatchdogFSM fsm;
    fsm.init();
    fsm.onMotionDetected();
    fsm.update(); // Now in STATE_WAIT_SHUTDOWN

    // Simulate Pi booting and working for 25 seconds
    MockArduinoPlatform::instance().advanceTimeMs(25000);
    fsm.update();
    run_test("Pi remains powered during execution", MockArduinoPlatform::instance().getPinValue(PIN_MOSFET_GATE) == LOW);

    // Pi signals shutdown complete: D6 goes HIGH
    MockArduinoPlatform::instance().setPinValue(PIN_SHUTDOWN_ACK, HIGH);
    fsm.update();
    run_test("State transitions to STATE_POWER_OFF_DELAY on ACK", fsm.getState() == WatchdogState::STATE_POWER_OFF_DELAY);

    // Advance 4999 ms (delay period not yet finished)
    MockArduinoPlatform::instance().advanceTimeMs(4999);
    fsm.update();
    run_test("Power remains ON during settling delay", MockArduinoPlatform::instance().getPinValue(PIN_MOSFET_GATE) == LOW);

    // Complete 5000 ms delay
    MockArduinoPlatform::instance().advanceTimeMs(2);
    fsm.update();
    run_test("Power cut OFF after settling delay (D8 HIGH)", MockArduinoPlatform::instance().getPinValue(PIN_MOSFET_GATE) == HIGH);
    run_test("FSM returns to STATE_SLEEP", fsm.getState() == WatchdogState::STATE_SLEEP);
}

void test_failsafe_timeout_force_cuts_power() {
    MockArduinoPlatform::instance().reset();
    WatchdogFSM fsm;
    fsm.init();
    fsm.onMotionDetected();
    fsm.update(); // STATE_WAIT_SHUTDOWN

    // Simulate 59 seconds elapsing without ACK
    MockArduinoPlatform::instance().advanceTimeMs(59000);
    fsm.update();
    run_test("Power still ON at 59 seconds", MockArduinoPlatform::instance().getPinValue(PIN_MOSFET_GATE) == LOW);
    run_test("Still in STATE_WAIT_SHUTDOWN at 59s", fsm.getState() == WatchdogState::STATE_WAIT_SHUTDOWN);

    // Advance to 60,001 ms (exceeding failsafe limit)
    MockArduinoPlatform::instance().advanceTimeMs(1001);
    fsm.update();
    run_test("Failsafe triggers: D8 HIGH (Power cut)", MockArduinoPlatform::instance().getPinValue(PIN_MOSFET_GATE) == HIGH);
    run_test("Returns to STATE_SLEEP after timeout", fsm.getState() == WatchdogState::STATE_SLEEP);
}

int main() {
    std::cout << "=== Running WatchdogFSM Unit Tests ===" << std::endl;
    test_initial_pin_configuration();
    test_motion_detection_triggers_power_on();
    test_shutdown_ack_and_clean_poweroff();
    test_failsafe_timeout_force_cuts_power();
    std::cout << "All tests completed." << std::endl;
    return 0;
}
