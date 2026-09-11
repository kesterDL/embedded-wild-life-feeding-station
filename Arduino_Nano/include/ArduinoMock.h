#ifndef ARDUINO_MOCK_H
#define ARDUINO_MOCK_H

#include <cstdint>
#include <map>
#include <vector>
#include <string>

// Standard Arduino Pin Logic Levels
#ifndef LOW
#define LOW  0x0
#endif
#ifndef HIGH
#define HIGH 0x1
#endif

// Pin Modes
#ifndef INPUT
#define INPUT 0x0
#endif
#ifndef OUTPUT
#define OUTPUT 0x1
#endif
#ifndef INPUT_PULLUP
#define INPUT_PULLUP 0x2
#endif

// Sleep Modes (simulating avr/sleep.h)
#define SLEEP_MODE_IDLE         0
#define SLEEP_MODE_ADC          1
#define SLEEP_MODE_PWR_DOWN     2
#define SLEEP_MODE_PWR_SAVE     3
#define SLEEP_MODE_STANDBY      4
#define SLEEP_MODE_EXT_STANDBY  5

// Interrupt modes
#define LOW_MODE     0
#define CHANGE       1
#define FALLING      2
#define RISING       3

class MockArduinoPlatform {
public:
    static MockArduinoPlatform& instance() {
        static MockArduinoPlatform inst;
        return inst;
    }

    void reset() {
        pinModes.clear();
        pinValues.clear();
        currentTimeMs = 0;
        sleepEnabled = false;
        sleepCount = 0;
        lastSleepMode = -1;
        interruptAttached = false;
        interruptPin = 0;
        interruptMode = 0;
        bodDisabled = false;
        adcDisabled = false;
    }

    // Pin Control
    void setPinMode(uint8_t pin, uint8_t mode) {
        pinModes[pin] = mode;
    }

    uint8_t getPinMode(uint8_t pin) const {
        auto it = pinModes.find(pin);
        return (it != pinModes.end()) ? it->second : INPUT;
    }

    void setPinValue(uint8_t pin, uint8_t val) {
        pinValues[pin] = val;
    }

    uint8_t getPinValue(uint8_t pin) const {
        auto it = pinValues.find(pin);
        return (it != pinValues.end()) ? it->second : LOW;
    }

    // Time Control
    unsigned long getTimeMs() const {
        return currentTimeMs;
    }

    void setTimeMs(unsigned long ms) {
        currentTimeMs = ms;
    }

    void advanceTimeMs(unsigned long ms) {
        currentTimeMs += ms;
    }

    // Sleep & Power Simulation
    bool sleepEnabled = false;
    int sleepCount = 0;
    int lastSleepMode = -1;
    bool bodDisabled = false;
    bool adcDisabled = false;

    // Interrupt Simulation
    bool interruptAttached = false;
    uint8_t interruptPin = 0;
    int interruptMode = 0;
    void (*isrCallback)() = nullptr;

    void triggerInterrupt() {
        if (interruptAttached && isrCallback) {
            isrCallback();
        }
    }

private:
    MockArduinoPlatform() { reset(); }
    std::map<uint8_t, uint8_t> pinModes;
    std::map<uint8_t, uint8_t> pinValues;
    unsigned long currentTimeMs = 0;
};

// Global Arduino function mocks
inline void pinMode(uint8_t pin, uint8_t mode) {
    MockArduinoPlatform::instance().setPinMode(pin, mode);
}

inline void digitalWrite(uint8_t pin, uint8_t val) {
    MockArduinoPlatform::instance().setPinValue(pin, val);
}

inline uint8_t digitalRead(uint8_t pin) {
    return MockArduinoPlatform::instance().getPinValue(pin);
}

inline unsigned long millis() {
    return MockArduinoPlatform::instance().getTimeMs();
}

inline void delay(unsigned long ms) {
    MockArduinoPlatform::instance().advanceTimeMs(ms);
}

inline void attachInterrupt(uint8_t interruptNum, void (*userFunc)(), int mode) {
    MockArduinoPlatform::instance().interruptAttached = true;
    MockArduinoPlatform::instance().interruptPin = interruptNum;
    MockArduinoPlatform::instance().isrCallback = userFunc;
    MockArduinoPlatform::instance().interruptMode = mode;
}

inline void detachInterrupt(uint8_t /*interruptNum*/) {
    MockArduinoPlatform::instance().interruptAttached = false;
    MockArduinoPlatform::instance().isrCallback = nullptr;
}

inline uint8_t digitalPinToInterrupt(uint8_t pin) {
    // On ATmega328P: Pin 2 -> INT0, Pin 3 -> INT1
    if (pin == 2) return 0;
    if (pin == 3) return 1;
    return 0xFF;
}

inline void set_sleep_mode(int mode) {
    MockArduinoPlatform::instance().lastSleepMode = mode;
}

inline void sleep_enable() {
    MockArduinoPlatform::instance().sleepEnabled = true;
}

inline void sleep_disable() {
    MockArduinoPlatform::instance().sleepEnabled = false;
}

inline void sleep_cpu() {
    MockArduinoPlatform::instance().sleepCount++;
}

inline void sleep_bod_disable() {
    MockArduinoPlatform::instance().bodDisabled = true;
}

#endif // ARDUINO_MOCK_H
