#include "include/WatchdogFSM.h"

WatchdogFSM watchdog;

void isrMotionWake() {
    // External hardware interrupt service routine for PIR motion detection (Pin D2 / INT0)
    watchdog.onMotionDetected();
}

void setup() {
    // Initialize pin modes, default power gate off, and prepare sleep
    watchdog.init();

    // Attach INT0 interrupt on RISING edge from HC-SR501 PIR sensor
    attachInterrupt(digitalPinToInterrupt(PIN_PIR_INTERRUPT), isrMotionWake, RISING);
}

void loop() {
    // Execute finite state machine tick
    watchdog.update();
}
