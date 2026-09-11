[ EDGE TIER (The Feeder) ]
       │
       ├─ (Physical Environment)
       │    └─> Sensor Array (PIR, Break Beam)
       │
       ├─ [ Watchdog Node (Arduino Nano) ]
       │    ├─ Hardware Interrupt Logic
       │    ├─ Battery Monitor
       │    └─ MOSFET Power Gate ────────┐ (Power & Signal)
       │                                 ▼
       └─ [ Media Node (Pi Zero W) ] ◄───┘
            ├─ Camera Initialization
            ├─ Local SD Ring Buffer
            └─ Wi-Fi Payload Transmission

[ INGESTION & GATEWAY TIER (Local Network) ]
       ▲
       │ (Wi-Fi)
       │
       ├─> [ Local MQTT Broker (Mosquitto) ]
       │    └─ Topic Routing (e.g., 'telemetry/feeder-1', 'alerts/motion')
       │
       └─> [ Local Object Storage (NAS) ]
            └─ Raw Video File Ingestion (MP4)

[ PROCESSING & STORAGE TIER (The Data Platform) ]
       ▲
       │ (Event Triggers & File Sync)
       │
       ├─> [ Event Consumer / Orchestrator ]
       │    ├─ Subscribes to MQTT topics
       │    ├─ Validates payload schemas
       │    └─ Triggers processing workflows (e.g., thumbnail extraction)
       │
       └─> [ Centralized Data Lakehouse ]
            ├─ Object Store: Persistent storage for video payloads
            └─ Metadata Catalog: Relational indexing of telemetry
               (timestamp, device_id, temperature, file_path)

[ SERVING & ALERTING TIER ]
       ▲
       │ (Processed Events & Queries)
       │
       ├─> [ Alerting Router ]
       │    └─ Push notifications (e.g., Home Assistant, Mobile App)
       │
       ├─> [ Live Feed Handler ]
       │    └─ Intermediary for on-demand asynchronous stream requests
       │
       └─> [ Fleet Management Dashboard ]
            └─ Visualizes node health, battery voltages, and detection metrics

[ INFRASTRUCTURE & AUTOMATION ]
       │
       └─> [ CI/CD Pipelines ]
            ├─ Infrastructure as Code (IaC) deployment for the data platform
            └─ Automated testing for event schemas and routing logic
