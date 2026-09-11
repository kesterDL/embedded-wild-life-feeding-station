# Technology Stack

## 1. Embedded Firmware (Watchdog Node)
- **Target Microcontroller:** Arduino Nano V3.0 (ATmega328P, 5V, 16 MHz)
- **Language / Standard:** C++ (C++11 / C++14) using the Arduino Core & AVR toolchain
- **Core Libraries:**
  - `<avr/sleep.h>`: Deep sleep state management (`SLEEP_MODE_PWR_DOWN`)
  - `<avr/interrupt.h>`: External hardware interrupt handling (`INT0` / Pin D2)
  - `<avr/power.h>`: Peripheral power reduction
- **Build / Tooling Options:** Arduino IDE 2.x, `arduino-cli`, or PlatformIO (Atmel AVR platform)

## 2. Linux Media Node (Raspberry Pi Zero W)
- **Target Platform:** Raspberry Pi Zero W (ARMv6, BCM2835)
- **Operating System:** Raspberry Pi OS Lite (32-bit, Debian-based)
- **Language / Runtime:** Python 3 (3.9+)
- **Hardware Interfacing:**
  - Camera Pipeline: `libcamera` / `rpicam-vid` CLI tools or `picamera2`
  - GPIO Control: `RPi.GPIO` or `gpiozero` for asserting the shutdown acknowledgment pin (GPIO 25)
- **Service Orchestration:** `systemd` one-shot / fork service (`squirrel-record.service`) triggered upon target boot
- **Storage & Filesystems:** USB OTG mass storage mounted to `/mnt/usb_storage` (supporting FAT32 and exFAT)

## 3. Sensors & Power Electronics
- **Motion Sensor:** HC-SR501 PIR sensor (3.3V active-high trigger, jumper in Repeatable 'H' mode)
- **Power Switching:** High-side P-Channel MOSFET switch with NPN BJT driver circuit
- **Camera Module:** 5MP / 8MP Raspberry Pi Camera Module connected via 15-pin CSI ribbon
- **Power Delivery:** 5V USB Power Bank (with low-draw keep-alive or always-on capability)
