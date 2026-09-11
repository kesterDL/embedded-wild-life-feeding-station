# Product Definition

## Product Vision
A self-contained, battery-powered edge camera system designed for wildlife monitoring at a backyard feeder. The system pairs an ultra-low-power Arduino Nano watchdog (ATmega328P) with a Raspberry Pi Zero W media node to balance micro-amp sleep power consumption with 1080p video recording capabilities.

## Target Audience & Use Case
- **Primary User:** Wildlife observers and edge computing enthusiasts deploying remote monitoring hardware in outdoor backyard environments.
- **Use Case:** Autonomous capture of high-definition video clips when animals visit the feeder, storing footage on a removable flash drive while withstanding outdoor temperatures and operating for weeks without battery replacement.

## Core Features (MVP)
1. **Ultra-Low-Power Standby:** Arduino Nano operates in deep sleep (`SLEEP_MODE_PWR_DOWN`), drawing micro-amps.
2. **Hardware Motion Detection:** HC-SR501 PIR motion sensor activates the Arduino via external hardware interrupt (`INT0`).
3. **Switched Power Distribution:** Arduino latches a P-MOSFET to supply regulated 5V power to the Raspberry Pi Zero W.
4. **Rapid Cold Boot & Media Pipeline:** Pi Zero W boots in under 15 seconds (network radios disabled), mounts USB storage, and records a 20-second 1080p video clip via CSI camera module.
5. **Zero Data Corruption Lifecycle:** Pipeline flushes filesystem buffers, asserts a GPIO handshake acknowledgment to the Arduino, and initiates a clean OS halt (`poweroff`).
6. **Hardware Power Isolation:** Arduino Nano monitors Pi shutdown acknowledgment, waits a safety margin for OS halt, cuts MOSFET power, and returns to sleep.
7. **Fail-Safe Watchdog Timer:** Arduino Nano enforces a 60-second hardware timeout to cut power if the Pi freezes or fails to signal shutdown.

## Future Horizons (Post-MVP)
- Multi-sensor fusion (dual PIR and IR beam-break to eliminate false triggers).
- Wi-Fi networking and MQTT event publishing.
- AWS IoT Core and S3 integration for remote cloud sync.
- "Wake-on-Event + Linger" window with on-demand live stream.
- Solar panel charging integration for indefinite deployment.
