# Implementation Plan: SquirrelFeeder MVP Implementation

Follow the Conductor TDD workflow: write failing unit/mock tests (Red), implement minimum code to pass (Green), refactor, and verify coverage (>80%).

## Phase 1: Arduino Nano Watchdog Firmware & Failsafe Timer
- [ ] Task: Setup Firmware Test Harness & Mock Scaffolding
    - [ ] Create unit test harness for Arduino state machine logic (simulating AVR pins, interrupts, and timers)
    - [ ] Verify test harness executes and tests fail (Red)
- [ ] Task: Implement FSM State Machine & Sleep Management
    - [ ] Implement core states: SLEEP, POWER_ON, WAIT_SHUTDOWN, POWER_OFF_DELAY
    - [ ] Implement AVR power management (ADCSRA disable, BOD disable, SLEEP_MODE_PWR_DOWN)
    - [ ] Verify state transitions pass test suite (Green)
- [ ] Task: Implement Hardware Interrupt & Power Gate Switching
    - [ ] Implement INT0 (D2) rising-edge ISR for PIR sensor trigger
    - [ ] Implement D8 MOSFET gate control (Active LOW on wake, Active HIGH to cut)
    - [ ] Implement D6 shutdown ACK pin polling/interrupt
- [ ] Task: Implement 60-Second Failsafe Watchdog Timer
    - [ ] Implement software/hardware timer tracking elapsed time in WAIT_SHUTDOWN state
    - [ ] Enforce power cutoff if ACK is not received within 60,000 ms
    - [ ] Implement 5,000 ms delay post-ACK before releasing D8 to ensure clean Linux OS halt
- [ ] Task: Phase Verification & Checkpoint (Refer to workflow.md)

## Phase 2: Pi Zero W Storage Manager & Fault Handling
- [ ] Task: Write Tests for USB Drive Detection & Mounting
    - [ ] Write unit tests for identifying USB block device (/dev/sd*)
    - [ ] Write unit tests for mount/unmount operations and missing-drive graceful abort
    - [ ] Verify tests fail (Red)
- [ ] Task: Implement Storage Manager Module
    - [ ] Implement USB drive detection and mount to /mnt/usb_storage
    - [ ] Implement fallback abort if USB drive is missing (preventing battery drain)
    - [ ] Implement sync and clean unmount before signaling shutdown
    - [ ] Verify tests pass (Green)
- [ ] Task: Write Tests & Implementation for File Naming & Directory Structure
    - [ ] Write unit tests for timestamped filename generation (e.g., clip_YYYYMMDD_HHMMSS.mp4)
    - [ ] Implement filename formatting and output directory creation (/mnt/usb_storage/videos/)
- [ ] Task: Phase Verification & Checkpoint (Refer to workflow.md)

## Phase 3: Pi Zero W Camera Pipeline & Lifecycle Daemon
- [ ] Task: Write Tests for Camera Pipeline Wrapper
    - [ ] Write unit tests for camera capture parameter generation (1080p, 30fps, 20s, MP4)
    - [ ] Write unit tests for handling camera hardware errors
    - [ ] Verify tests fail (Red)
- [ ] Task: Implement Camera Service Module
    - [ ] Implement libcamera-vid / rpicam-vid subprocess wrapper targeting MP4 output
    - [ ] Verify camera service passes unit tests (Green)
- [ ] Task: Write Tests & Implementation for Watchdog GPIO Handshake
    - [ ] Write unit tests for GPIO 25 pin assertion
    - [ ] Implement GPIO 25 active-HIGH pulse to acknowledge shutdown to Nano
- [ ] Task: Implement Master Orchestrator Script
    - [ ] Chain sequence: Mount Storage -> Record Video -> Sync Disk -> Signal ACK -> OS Poweroff
    - [ ] Verify orchestrator end-to-end flow with mocked hardware
- [ ] Task: Phase Verification & Checkpoint (Refer to workflow.md)

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
