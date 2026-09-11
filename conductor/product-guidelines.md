# Product Guidelines

## Engineering & Architecture Principles
1. **Defensive Hardware Control:**
   - Default all power-switching GPIOs to safe/inactive states upon boot and reset.
   - Always enforce hardware watchdog timeouts (e.g., 60-second limit) so an unresponsive Linux node cannot drain the battery indefinitely.
2. **Zero-Corruption File Lifecycle:**
   - Synchronize and flush all disk buffers (`sync`) before asserting shutdown acknowledgments.
   - Provide adequate OS halt settling time (e.g., 5 seconds after acknowledgment) before cutting physical power.
   - If removable media is absent or unmountable, abort execution cleanly and signal shutdown immediately to avoid battery waste.
3. **Power Budget Discipline:**
   - Disable all unused hardware peripherals and radios (Wi-Fi, Bluetooth, HDMI, status LEDs where feasible).
   - Maximize deep sleep duration (`SLEEP_MODE_PWR_DOWN`) on the watchdog microcontroller.
4. **Deterministic State Machine Design:**
   - Structure firmware and daemon scripts as explicit finite state machines (FSM) with validated transitions and timeout handling.
   - Log critical events with timestamps or relative uptime indicators for debugging.

## Code Quality & Documentation Standards
- **Pin & Register Transparency:** Explicitly document physical pin numbers, BCM GPIO channels, interrupt vectors, and electrical characteristics.
- **Fail-Safe Defaults:** Code must recover or enter safe sleep mode on unexpected inputs or exceptions.
- **Self-Documenting Code:** Clear variable naming reflecting hardware signals (e.g., `PIN_MOSFET_GATE`, `PIN_SHUTDOWN_ACK`).
