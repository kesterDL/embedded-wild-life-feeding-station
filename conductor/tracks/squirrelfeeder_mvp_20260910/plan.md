# Implementation Plan: SquirrelFeeder MVP Implementation

Follow the Conductor TDD workflow: write failing unit/mock tests (Red), implement minimum code to pass (Green), refactor, and verify coverage (>80%).

## Phase 1: Arduino Nano Watchdog Firmware & Failsafe Timer
- [x] Task: Setup Firmware Test Harness & Mock Scaffolding
    - [x] Create unit test harness for Arduino state machine logic (simulating AVR pins, interrupts, and timers)
    - [x] Verify test harness executes and tests fail (Red)
- [x] Task: Implement FSM State Machine & Sleep Management
    - [x] Implement core states: SLEEP, POWER_ON, WAIT_SHUTDOWN, POWER_OFF_DELAY
    - [x] Implement AVR power management (ADCSRA disable, BOD disable, SLEEP_MODE_PWR_DOWN)
    - [x] Verify state transitions pass test suite (Green)
- [x] Task: Implement Hardware Interrupt & Power Gate Switching
    - [x] Implement INT0 (D2) rising-edge ISR for PIR sensor trigger
    - [x] Implement D8 MOSFET gate control (Active LOW on wake, Active HIGH to cut)
    - [x] Implement D6 shutdown ACK pin polling/interrupt
- [x] Task: Implement 60-Second Failsafe Watchdog Timer
    - [x] Implement software/hardware timer tracking elapsed time in WAIT_SHUTDOWN state
    - [x] Enforce power cutoff if ACK is not received within 60,000 ms
    - [x] Implement 5,000 ms delay post-ACK before releasing D8 to ensure clean Linux OS halt
- [x] Task: Phase Verification & Checkpoint (Refer to workflow.md)

## Phase 2: Pi Zero W Storage Manager & Fault Handling
- [x] Task: Write Tests for USB Drive Detection & Mounting
    - [x] Write unit tests for identifying USB block device (/dev/sd*)
    - [x] Write unit tests for mount/unmount operations and missing-drive graceful abort
    - [x] Verify tests fail (Red)
- [x] Task: Implement Storage Manager Module
    - [x] Implement USB drive detection and mount to /mnt/usb_storage
    - [x] Implement fallback abort if USB drive is missing (preventing battery drain)
    - [x] Implement sync and clean unmount before signaling shutdown
    - [x] Verify tests pass (Green)
- [x] Task: Write Tests & Implementation for File Naming & Directory Structure
    - [x] Write unit tests for timestamped filename generation (e.g., clip_YYYYMMDD_HHMMSS.mp4)
    - [x] Implement filename formatting and output directory creation (/mnt/usb_storage/videos/)
- [x] Task: Phase Verification & Checkpoint (Refer to workflow.md)

## Phase 3: Pi Zero W Camera Pipeline & Lifecycle Daemon
- [x] Task: Write Tests for Camera Pipeline Wrapper
    - [x] Write unit tests for camera capture parameter generation (1080p, 30fps, 20s, MP4)
    - [x] Write unit tests for handling camera hardware errors
    - [x] Verify tests fail (Red)
- [x] Task: Implement Camera Service Module
    - [x] Implement libcamera-vid / rpicam-vid subprocess wrapper targeting MP4 output
    - [x] Verify camera service passes unit tests (Green)
- [x] Task: Write Tests & Implementation for Watchdog GPIO Handshake
    - [x] Write unit tests for GPIO 25 pin assertion
    - [x] Implement GPIO 25 active-HIGH pulse to acknowledge shutdown to Nano
- [x] Task: Implement Master Orchestrator Script
    - [x] Chain sequence: Mount Storage -> Record Video -> Sync Disk -> Signal ACK -> OS Poweroff
    - [x] Verify orchestrator end-to-end flow with mocked hardware
- [~] Task: Phase Verification & Checkpoint (Refer to workflow.md)

## Phase 4: OS Optimization, Systemd Automation, & Integration
- [ ] Task: Create Fast-Boot Systemd Service
    - [ ] Create squirrel-record.service unit file with dependencies and fast-boot ordering
    - [ ] Add verification test for service syntax and execution permissions
- [ ] Task: Create OS Boot Optimization Script
    - [ ] Create script to disable HDMI (tvservice -o), Bluetooth, Wi-Fi, and non-essential services
- [ ] Task: System Integration Verification
    - [ ] Verify Arduino Nano .ino / PlatformIO compilation
    - [ ] Verify full mock end-to-end execution of the Python media pipeline
- [ ] Task: Phase Verification & Checkpoint (Refer to workflow.md)
