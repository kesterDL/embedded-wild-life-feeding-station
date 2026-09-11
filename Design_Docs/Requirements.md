# System Requirements

## 1.0 Summary

A battery-powered, edge-deployed camera system monitoring a backyard wildlife feeder. The system integrates ultra-low-power environmental sensing with a Linux-based video pipeline. Video payloads are routed to local network storage with MQTT alerting, establishing a foundational architecture designed for future migration to AWS IoT Core and S3.

## 1.1 Motivation

To build a robust IoT edge node that bridges hardware integration, custom weather-sealed enclosure fabrication, and event-driven data pipelines. This project serves as a practical deployment of edge computing and sensor fusion, overcoming physical environmental challenges while maintaining strict power efficiency.

## 2.0 Dual Hardware Strategy

The system utilizes a dual-architecture pattern to balance ultra-low power consumption with heavy-lifting media processing capabilities:

**2.1 Watchdog Node (Arduino Nano):** Operates continuously in a micro-amp deep sleep state. It manages hardware interrupts from a fused sensor array (e.g., PIR and IR Break Beam). Upon validating a true positive motion event, it latches a MOSFET to deliver physical power to the media node.

**2.2 Media & Network Node (Raspberry Pi Zero W):** Boots only when powered by the Nano. It initializes the camera, connects to Wi-Fi, records the subject, publishes an MQTT alert, and transfers the video payload. Upon completing its pipeline, it signals the Nano via a GPIO pin to sever power, returning the entire system to a dormant state.

## 3.0 Functional Requirements

**3.1 Sensor Fusion Activation:** The Nano must read multiple interrupt sources to filter out thermal false positives before triggering the Pi Zero.

**3.2 Automated Lifecycle Management:** The Pi Zero must execute a graceful shutdown sequence and signal the Nano to cut power immediately after data transfer.

**3.3 Local Media Pipeline:** Video clips must be buffered locally and pushed to a local network drive, simultaneously publishing state events to an MQTT broker.

**3.4 Asynchronous Live Feed:** The system must implement a "Wake-on-Event + Linger" window, keeping the Pi active for 3 to 5 minutes post-recording to allow on-demand live stream access from a dashboard.

## 4.0 Non-Functional Requirements

**4.1 Power Autonomy:** The system must operate on high-capacity battery cells (e.g., 18650s) with a power budget supporting weeks of standby, engineered to accommodate future solar charging integration.

**4.2 Thermal Resilience:** The physical enclosure and sensor logic must withstand local ambient summer temperatures exceeding 100°F without degrading detection accuracy or damaging components.

**4.3 Network Fault Tolerance:** The system must utilize a local SD card ring buffer to prevent video data loss during Wi-Fi dropouts, automatically syncing upon reconnection.

**4.4 Cloud Extensibility:** MQTT topic structures and network payloads must be formatted to seamlessly bridge with AWS IoT Core rules and S3 event triggers in later iterations.
