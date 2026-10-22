#!/usr/bin/env python3
"""Wildlife Feeder Metrics & Diagnostics Visualization Tool.

Parses lifecycle.log and video recordings directory to generate a standalone,
offline-capable, interactive HTML dashboard visualizing start-up latency, power brownouts,
cycle phase breakdowns, reliability rates, and file payloads.

Usage:
    python3 Pi_Zero/scripts/visualize_metrics.py
    python3 Pi_Zero/scripts/visualize_metrics.py --log /path/to/lifecycle.log --open
    python3 Pi_Zero/scripts/visualize_metrics.py --output /path/to/dashboard.html
"""

import argparse
import csv
import json
import logging
import os
import re
import sys
import webbrowser
from typing import Any, Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("VisualizeMetrics")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
DEFAULT_RECORDINGS_DIR = os.path.join(REPO_ROOT, "Wild_Life_Recordings")
DEFAULT_LOG_NAME = "lifecycle.log"
DEFAULT_OUTPUT_NAME = "metrics_dashboard.html"
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
CHART_JS_ASSET = os.path.join(ASSETS_DIR, "chart.umd.min.js")


def decode_throttled_bitmask(throttled_str: Optional[str]) -> Dict[str, Any]:
    """Decodes Raspberry Pi vcgencmd get_throttled hex string into hardware diagnostic flags.

    Bitmask reference:
      Bit  0 (0x1):     Under-voltage detected now (active)
      Bit  1 (0x2):     Arm frequency capped now (active)
      Bit  2 (0x4):     Currently throttled now (active)
      Bit  3 (0x8):     Soft temperature limit active now
      Bit 16 (0x10000): Under-voltage has occurred since last reboot
      Bit 17 (0x20000): Arm frequency capping has occurred
      Bit 18 (0x40000): Throttling has occurred since last reboot
      Bit 19 (0x80000): Soft temperature limit has occurred
    """
    if not throttled_str or throttled_str in ("N/A", "UNKNOWN", "none"):
        return {
            "raw_hex": "0x0",
            "val": 0,
            "is_throttled": False,
            "active_undervoltage": False,
            "active_throttling": False,
            "past_undervoltage": False,
            "past_throttling": False,
            "badge": "pwrOK",
            "description": "Clean Power (Normal, no throttling)",
        }

    match = re.search(r"0x([0-9a-fA-F]+)", str(throttled_str))
    val = 0
    if match:
        try:
            val = int(match.group(1), 16)
        except ValueError:
            val = 0

    active_uv = bool(val & 0x1)
    active_th = bool(val & 0x4)
    past_uv = bool(val & 0x10000)
    past_th = bool(val & 0x40000)
    is_throttled = val > 0

    desc_parts = []
    if active_uv:
        desc_parts.append("Active Under-voltage (<4.63V)")
    if active_th:
        desc_parts.append("Active CPU Throttling")
    if past_uv and not active_uv:
        desc_parts.append("Historical Under-voltage")
    if past_th and not active_th:
        desc_parts.append("Historical Throttling")

    desc = ", ".join(desc_parts) if desc_parts else "Clean Power (Normal)"

    return {
        "raw_hex": f"0x{val:x}",
        "val": val,
        "is_throttled": is_throttled,
        "active_undervoltage": active_uv,
        "active_throttling": active_th,
        "past_undervoltage": past_uv,
        "past_throttling": past_th,
        "badge": "pwrWARN" if is_throttled else "pwrOK",
        "description": desc,
    }


def _safe_float(val: Any) -> Optional[float]:
    try:
        if val is None or val == "" or str(val).strip().upper() == "N/A":
            return None
        return float(val)
    except (TypeError, ValueError):
        return None


def parse_lifecycle_log(log_path: str) -> List[Dict[str, Any]]:
    """Parses lifecycle CSV log file into structured cycle dictionaries."""
    if not os.path.exists(log_path):
        logger.warning(f"Log file not found: {log_path}")
        return []

    records = []
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader):
                raw_uptime = _safe_float(row.get("uptime_s"))
                raw_record = _safe_float(row.get("record_s"))
                raw_mux = _safe_float(row.get("mux_s"))
                raw_cycle = _safe_float(row.get("total_cycle_s"))
                status = (row.get("status") or "UNKNOWN").strip()
                vfile = (row.get("video_file") or "none").strip()
                throttled_raw = (row.get("throttled") or "throttled=0x0").strip()

                diag = decode_throttled_bitmask(throttled_raw)

                # Extract sequence number if available
                seq_match = re.search(r"clip_(\d+)", vfile)
                seq_num = int(seq_match.group(1)) if seq_match else idx + 1

                records.append({
                    "cycle_index": idx + 1,
                    "seq": seq_num,
                    "timestamp": row.get("timestamp", "").strip(),
                    "uptime_s": raw_uptime,
                    "record_s": raw_record if raw_record is not None else 0.0,
                    "mux_s": raw_mux if raw_mux is not None else 0.0,
                    "total_cycle_s": raw_cycle if raw_cycle is not None else 0.0,
                    "status": status,
                    "video_file": vfile,
                    "throttled": throttled_raw,
                    "raw_hex": diag["raw_hex"],
                    "is_throttled": diag["is_throttled"],
                    "active_undervoltage": diag["active_undervoltage"],
                    "active_throttling": diag["active_throttling"],
                    "badge": diag["badge"],
                    "power_desc": diag["description"],
                })
    except Exception as e:
        logger.error(f"Error reading {log_path}: {e}")

    return records


def compute_kpis(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Computes high-level Key Performance Indicators across recorded cycles."""
    total = len(records)
    if total == 0:
        return {
            "total_cycles": 0,
            "cold_boot_cycles": 0,
            "success_count": 0,
            "camera_error_count": 0,
            "storage_error_count": 0,
            "failure_count": 0,
            "success_rate_pct": 0.0,
            "clean_power_count": 0,
            "brownout_count": 0,
            "brownout_rate_pct": 0.0,
            "avg_uptime_clean_s": 0.0,
            "avg_uptime_brownout_s": 0.0,
            "avg_record_s": 0.0,
            "avg_mux_s": 0.0,
            "avg_total_cycle_s": 0.0,
        }

    # Separate cold boots from long maintenance/bench sessions (> 600s)
    cold_boots = [r for r in records if r["uptime_s"] is not None and r["uptime_s"] < 600]

    successes = sum(1 for r in records if r["status"] == "SUCCESS")
    camera_errors = sum(1 for r in records if r["status"] == "CAMERA_ERROR")
    storage_errors = sum(1 for r in records if r["status"] == "STORAGE_ERROR")
    failures = total - successes

    clean_cold = [r for r in cold_boots if not r["is_throttled"]]
    brownout_cold = [r for r in cold_boots if r["is_throttled"]]

    avg_up_clean = (
        sum(r["uptime_s"] for r in clean_cold) / len(clean_cold) if clean_cold else 0.0
    )
    avg_up_brownout = (
        sum(r["uptime_s"] for r in brownout_cold) / len(brownout_cold) if brownout_cold else 0.0
    )

    clean_succ = [r for r in cold_boots if r["status"] == "SUCCESS"]
    avg_rec = sum(r["record_s"] for r in clean_succ) / len(clean_succ) if clean_succ else 0.0
    # Exclude runaway muxing from benchmarks when calculating average
    valid_mux = [r["mux_s"] for r in clean_succ if r["mux_s"] < 100]
    avg_mux = sum(valid_mux) / len(valid_mux) if valid_mux else 0.0
    valid_cycle = [r["total_cycle_s"] for r in clean_succ if r["total_cycle_s"] < 200]
    avg_cycle = sum(valid_cycle) / len(valid_cycle) if valid_cycle else 0.0

    return {
        "total_cycles": total,
        "cold_boot_cycles": len(cold_boots),
        "success_count": successes,
        "camera_error_count": camera_errors,
        "storage_error_count": storage_errors,
        "failure_count": failures,
        "success_rate_pct": round(successes / total * 100, 1),
        "clean_power_count": len(clean_cold),
        "brownout_count": len(brownout_cold),
        "brownout_rate_pct": round(len(brownout_cold) / len(cold_boots) * 100, 1) if cold_boots else 0.0,
        "avg_uptime_clean_s": round(avg_up_clean, 2),
        "avg_uptime_brownout_s": round(avg_up_brownout, 2),
        "avg_record_s": round(avg_rec, 2),
        "avg_mux_s": round(avg_mux, 2),
        "avg_total_cycle_s": round(avg_cycle, 2),
    }


def get_file_sizes(recordings_dir: str, records: List[Dict[str, Any]]) -> Dict[str, float]:
    """Finds actual or inferred file sizes in MB for recorded video files."""
    sizes = {}
    for r in records:
        vfile = r["video_file"]
        if vfile and vfile != "none":
            path = os.path.join(recordings_dir, vfile)
            if os.path.exists(path):
                sizes[vfile] = round(os.path.getsize(path) / (1024 * 1024), 2)
            else:
                # Estimate: 20s at 10Mbps = ~23.8 MB if SUCCESS, 0 MB if CAMERA_ERROR
                sizes[vfile] = 23.8 if r["status"] == "SUCCESS" else 0.0
        else:
            sizes[vfile] = 0.0
    return sizes


def generate_html_dashboard(
    records: List[Dict[str, Any]],
    recordings_dir: str,
    output_path: str
) -> str:
    """Generates a self-contained, offline-first interactive HTML dashboard."""
    kpis = compute_kpis(records)
    file_sizes = get_file_sizes(recordings_dir, records)

    # Attach file sizes to records
    for r in records:
        r["size_mb"] = file_sizes.get(r["video_file"], 0.0)

    # Load offline Chart.js bundle
    chartjs_code = ""
    if os.path.exists(CHART_JS_ASSET):
        try:
            with open(CHART_JS_ASSET, "r", encoding="utf-8") as f:
                chartjs_code = f.read()
        except OSError as e:
            logger.warning(f"Could not read local Chart.js asset: {e}")

    # Prepare datasets for Chart.js
    chart_records = [r for r in records if r["uptime_s"] is not None and r["uptime_s"] < 600]
    if not chart_records:
        chart_records = records

    labels = [f"#{r['cycle_index']} ({r['timestamp'].split()[-1] if r['timestamp'] else r['seq']})" for r in chart_records]
    uptimes = [r["uptime_s"] if r["uptime_s"] is not None else 0.0 for r in chart_records]
    power_colors = [
        "rgba(239, 68, 68, 0.85)" if r["is_throttled"] else "rgba(16, 185, 129, 0.85)"
        for r in chart_records
    ]
    power_borders = [
        "#ef4444" if r["is_throttled"] else "#10b981"
        for r in chart_records
    ]

    record_durations = [r["record_s"] for r in chart_records]
    mux_durations = [r["mux_s"] if r["mux_s"] < 100 else 0.0 for r in chart_records]

    # Status distribution
    status_counts: Dict[str, int] = {}
    for r in records:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1

    # Payload sizes
    sizes_data = [r["size_mb"] for r in chart_records]

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Squirrel Feeder — Metrics & Diagnostics Dashboard</title>
<style>
  :root {{
    --bg-primary: #0f172a;
    --bg-secondary: #1e293b;
    --bg-card: #1e293b;
    --border-color: #334155;
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
    --accent-blue: #38bdf8;
    --accent-emerald: #10b981;
    --accent-rose: #f43f5e;
    --accent-amber: #f59e0b;
    --accent-purple: #a855f7;
    --radius-md: 12px;
    --shadow-card: 0 4px 6px -1px rgba(0, 0, 0, 0.3), 0 2px 4px -2px rgba(0, 0, 0, 0.2);
  }}

  * {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }}

  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    background-color: var(--bg-primary);
    color: var(--text-primary);
    line-height: 1.5;
    padding: 24px;
  }}

  .container {{
    max-width: 1440px;
    margin: 0 auto;
  }}

  header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-bottom: 24px;
    border-bottom: 1px solid var(--border-color);
    margin-bottom: 24px;
    flex-wrap: wrap;
    gap: 16px;
  }}

  .header-title h1 {{
    font-size: 1.75rem;
    font-weight: 700;
    letter-spacing: -0.025em;
    color: var(--text-primary);
    display: flex;
    align-items: center;
    gap: 10px;
  }}

  .header-title p {{
    color: var(--text-secondary);
    font-size: 0.9rem;
    margin-top: 4px;
  }}

  .header-badge {{
    background: rgba(56, 189, 248, 0.1);
    color: var(--accent-blue);
    border: 1px solid rgba(56, 189, 248, 0.2);
    padding: 6px 14px;
    border-radius: 9999px;
    font-size: 0.82rem;
    font-weight: 600;
  }}

  /* KPI Cards Grid */
  .kpi-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
  }}

  .kpi-card {{
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    padding: 20px;
    box-shadow: var(--shadow-card);
    position: relative;
    overflow: hidden;
  }}

  .kpi-card::before {{
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 4px;
    background: var(--card-accent, var(--accent-blue));
  }}

  .kpi-card.emerald {{ --card-accent: var(--accent-emerald); }}
  .kpi-card.amber {{ --card-accent: var(--accent-amber); }}
  .kpi-card.rose {{ --card-accent: var(--accent-rose); }}
  .kpi-card.purple {{ --card-accent: var(--accent-purple); }}

  .kpi-title {{
    font-size: 0.82rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-secondary);
  }}

  .kpi-value {{
    font-size: 2rem;
    font-weight: 700;
    margin-top: 6px;
    letter-spacing: -0.03em;
    color: var(--text-primary);
  }}

  .kpi-subtitle {{
    font-size: 0.82rem;
    color: var(--text-muted);
    margin-top: 6px;
  }}

  /* Visual Panels Grid */
  .panels-grid {{
    display: grid;
    grid-template-columns: repeat(12, 1fr);
    gap: 20px;
    margin-bottom: 24px;
  }}

  .panel {{
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    padding: 20px;
    box-shadow: var(--shadow-card);
  }}

  .col-12 {{ grid-column: span 12; }}
  .col-8 {{ grid-column: span 8; }}
  .col-6 {{ grid-column: span 6; }}
  .col-4 {{ grid-column: span 4; }}

  @media (max-width: 1024px) {{
    .col-8, .col-6, .col-4 {{ grid-column: span 12; }}
  }}

  .panel-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
  }}

  .panel-title {{
    font-size: 1rem;
    font-weight: 600;
    color: var(--text-primary);
    display: flex;
    align-items: center;
    gap: 8px;
  }}

  .chart-container {{
    position: relative;
    width: 100%;
    height: 320px;
  }}

  /* Badges */
  .badge {{
    display: inline-block;
    padding: 3px 8px;
    border-radius: 6px;
    font-size: 0.75rem;
    font-weight: 600;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  }}

  .badge-ok {{
    background: rgba(16, 185, 129, 0.15);
    color: var(--accent-emerald);
    border: 1px solid rgba(16, 185, 129, 0.3);
  }}

  .badge-warn {{
    background: rgba(244, 63, 94, 0.15);
    color: var(--accent-rose);
    border: 1px solid rgba(244, 63, 94, 0.3);
  }}

  .badge-success {{
    background: rgba(56, 189, 248, 0.15);
    color: var(--accent-blue);
    border: 1px solid rgba(56, 189, 248, 0.3);
  }}

  .badge-error {{
    background: rgba(244, 63, 94, 0.15);
    color: var(--accent-rose);
    border: 1px solid rgba(244, 63, 94, 0.3);
  }}

  /* Table */
  .table-controls {{
    display: flex;
    gap: 12px;
    margin-bottom: 16px;
    flex-wrap: wrap;
  }}

  .search-input, .filter-select {{
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    color: var(--text-primary);
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 0.85rem;
    outline: none;
  }}

  .search-input:focus, .filter-select:focus {{
    border-color: var(--accent-blue);
  }}

  .table-responsive {{
    overflow-x: auto;
    max-height: 480px;
  }}

  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
    text-align: left;
  }}

  th {{
    background: var(--bg-primary);
    color: var(--text-secondary);
    padding: 10px 14px;
    font-weight: 600;
    position: sticky;
    top: 0;
    z-index: 10;
    border-bottom: 1px solid var(--border-color);
  }}

  td {{
    padding: 10px 14px;
    border-bottom: 1px solid rgba(51, 65, 85, 0.5);
    color: var(--text-primary);
  }}

  tr:hover td {{
    background: rgba(255, 255, 255, 0.02);
  }}

  .mono {{
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 0.8rem;
  }}
</style>
{f'<script>{chartjs_code}</script>' if chartjs_code else '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>'}
</head>
<body>

<div class="container">
  <header>
    <div class="header-title">
      <h1>🐿️ Squirrel Feeder Diagnostics</h1>
      <p>Performance, Start-up Latency & Power Brownout Metrics Dashboard</p>
    </div>
    <div class="header-badge">
      ⚡ Offline-First Bundle
    </div>
  </header>

  <!-- KPI Top Cards -->
  <div class="kpi-grid">
    <div class="kpi-card emerald">
      <div class="kpi-title">Total Capture Cycles</div>
      <div class="kpi-value">{kpis['total_cycles']}</div>
      <div class="kpi-subtitle">{kpis['cold_boot_cycles']} cold-boot triggers recorded</div>
    </div>
    <div class="kpi-card purple">
      <div class="kpi-title">Capture Success Rate</div>
      <div class="kpi-value">{kpis['success_rate_pct']}%</div>
      <div class="kpi-subtitle">{kpis['success_count']} successes / {kpis['failure_count']} errors</div>
    </div>
    <div class="kpi-card {'amber' if kpis['brownout_rate_pct'] > 15 else 'emerald'}">
      <div class="kpi-title">Power Brownout Rate</div>
      <div class="kpi-value">{kpis['brownout_rate_pct']}%</div>
      <div class="kpi-subtitle">{kpis['brownout_count']} brownout cycles (0x50005)</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-title">Avg Start-up Time</div>
      <div class="kpi-value">{kpis['avg_uptime_clean_s']}s <span style="font-size: 1rem; color: var(--accent-rose); font-weight: normal;">/ {kpis['avg_uptime_brownout_s']}s ⚠️</span></div>
      <div class="kpi-subtitle">Clean Power ({kpis['avg_uptime_clean_s']}s) vs Brownout ({kpis['avg_uptime_brownout_s']}s)</div>
    </div>
  </div>

  <!-- Panels Grid -->
  <div class="panels-grid">
    <!-- Panel 1: Start-up Latency Timeline -->
    <div class="panel col-8">
      <div class="panel-header">
        <div class="panel-title">📈 Start-up Boot Latency vs Power State</div>
        <div>
          <span class="badge badge-ok">● pwrOK (0x0)</span>
          <span class="badge badge-warn">● pwrWARN (0x50005)</span>
        </div>
      </div>
      <div class="chart-container">
        <canvas id="startupChart"></canvas>
      </div>
    </div>

    <!-- Panel 3: Reliability & Error Donut -->
    <div class="panel col-4">
      <div class="panel-header">
        <div class="panel-title">🎯 Reliability Distribution</div>
      </div>
      <div class="chart-container">
        <canvas id="reliabilityChart"></canvas>
      </div>
    </div>

    <!-- Panel 2: Cycle Phase Timing Breakdown -->
    <div class="panel col-6">
      <div class="panel-header">
        <div class="panel-title">⏱️ Cycle Phase Timing Breakdown</div>
      </div>
      <div class="chart-container">
        <canvas id="phaseChart"></canvas>
      </div>
    </div>

    <!-- Panel 4: Recording Payload Sizes -->
    <div class="panel col-6">
      <div class="panel-header">
        <div class="panel-title">📦 Recording Payload Sizes (MB)</div>
      </div>
      <div class="chart-container">
        <canvas id="payloadChart"></canvas>
      </div>
    </div>

    <!-- Panel 5: Searchable Data Table -->
    <div class="panel col-12">
      <div class="panel-header">
        <div class="panel-title">📋 Comprehensive Lifecycle Event Log</div>
      </div>
      <div class="table-controls">
        <input type="text" id="searchInput" class="search-input" placeholder="Search filename or status..." onkeyup="filterTable()">
        <select id="statusFilter" class="filter-select" onchange="filterTable()">
          <option value="ALL">All Statuses</option>
          <option value="SUCCESS">SUCCESS</option>
          <option value="CAMERA_ERROR">CAMERA_ERROR</option>
          <option value="STORAGE_ERROR">STORAGE_ERROR</option>
        </select>
        <select id="powerFilter" class="filter-select" onchange="filterTable()">
          <option value="ALL">All Power States</option>
          <option value="pwrOK">Clean Power (pwrOK)</option>
          <option value="pwrWARN">Brownout (pwrWARN)</option>
        </select>
      </div>
      <div class="table-responsive">
        <table id="metricsTable">
          <thead>
            <tr>
              <th>#</th>
              <th>Timestamp</th>
              <th>Status</th>
              <th>Power State</th>
              <th>Uptime (Boot)</th>
              <th>Record</th>
              <th>Mux</th>
              <th>Total Cycle</th>
              <th>Payload</th>
              <th>Video File</th>
            </tr>
          </thead>
          <tbody>
"""

    for r in records:
        status_cls = "badge-success" if r["status"] == "SUCCESS" else "badge-error"
        pwr_cls = "badge-ok" if not r["is_throttled"] else "badge-warn"
        uptime_disp = f"{r['uptime_s']:.2f}s" if r["uptime_s"] is not None else "N/A"
        size_disp = f"{r['size_mb']:.2f} MB" if r["size_mb"] > 0 else "0.00 MB"

        html_content += f"""            <tr>
              <td class="mono">#{r['cycle_index']}</td>
              <td>{r['timestamp']}</td>
              <td><span class="badge {status_cls}">{r['status']}</span></td>
              <td><span class="badge {pwr_cls}" title="{r['power_desc']}">{r['badge']} ({r['raw_hex']})</span></td>
              <td class="mono">{uptime_disp}</td>
              <td class="mono">{r['record_s']:.2f}s</td>
              <td class="mono">{r['mux_s']:.2f}s</td>
              <td class="mono">{r['total_cycle_s']:.2f}s</td>
              <td class="mono">{size_disp}</td>
              <td class="mono">{r['video_file']}</td>
            </tr>
"""

    html_content += f"""          </tbody>
        </table>
      </div>
    </div>
  </div>
</div>

<script>
  // Chart.js Configuration
  const chartLabels = {json.dumps(labels)};
  const uptimesData = {json.dumps(uptimes)};
  const powerColors = {json.dumps(power_colors)};
  const powerBorders = {json.dumps(power_borders)};
  const recordData = {json.dumps(record_durations)};
  const muxData = {json.dumps(mux_durations)};
  const payloadData = {json.dumps(sizes_data)};

  // 1. Startup Latency Chart
  new Chart(document.getElementById('startupChart'), {{
    type: 'bar',
    data: {{
      labels: chartLabels,
      datasets: [{{
        label: 'Start-up Uptime (s)',
        data: uptimesData,
        backgroundColor: powerColors,
        borderColor: powerBorders,
        borderWidth: 1,
        borderRadius: 4
      }}]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          callbacks: {{
            afterLabel: function(ctx) {{
              const isThrottled = powerColors[ctx.dataIndex].includes('239');
              return isThrottled ? 'Power: BROWNOUT (0x50005)' : 'Power: Clean (0x0)';
            }}
          }}
        }}
      }},
      scales: {{
        y: {{
          title: {{ display: true, text: 'Uptime (Seconds)', color: '#94a3b8' }},
          grid: {{ color: '#334155' }},
          ticks: {{ color: '#94a3b8' }}
        }},
        x: {{
          grid: {{ display: false }},
          ticks: {{ color: '#94a3b8', maxRotation: 45, minRotation: 45 }}
        }}
      }}
    }}
  }});

  // 2. Reliability Donut Chart
  const statusLabels = {json.dumps(list(status_counts.keys()))};
  const statusValues = {json.dumps(list(status_counts.values()))};
  const statusColors = statusLabels.map(l => l === 'SUCCESS' ? '#38bdf8' : (l === 'CAMERA_ERROR' ? '#f43f5e' : '#f59e0b'));

  new Chart(document.getElementById('reliabilityChart'), {{
    type: 'doughnut',
    data: {{
      labels: statusLabels,
      datasets: [{{
        data: statusValues,
        backgroundColor: statusColors,
        borderWidth: 0
      }}]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      plugins: {{
        legend: {{
          position: 'bottom',
          labels: {{ color: '#94a3b8', boxWidth: 12 }}
        }}
      }}
    }}
  }});

  // 3. Cycle Phase Breakdown (Stacked Bar)
  new Chart(document.getElementById('phaseChart'), {{
    type: 'bar',
    data: {{
      labels: chartLabels,
      datasets: [
        {{
          label: 'Boot Uptime',
          data: uptimesData,
          backgroundColor: '#3b82f6',
          borderRadius: 2
        }},
        {{
          label: 'Record Duration',
          data: recordData,
          backgroundColor: '#10b981',
          borderRadius: 2
        }},
        {{
          label: 'Mux Duration',
          data: muxData,
          backgroundColor: '#a855f7',
          borderRadius: 2
        }}
      ]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      scales: {{
        x: {{ stacked: true, grid: {{ display: false }}, ticks: {{ color: '#94a3b8', maxRotation: 45 }} }},
        y: {{ stacked: true, grid: {{ color: '#334155' }}, ticks: {{ color: '#94a3b8' }}, title: {{ display: true, text: 'Seconds', color: '#94a3b8' }} }}
      }},
      plugins: {{
        legend: {{ labels: {{ color: '#94a3b8' }} }}
      }}
    }}
  }});

  // 4. Payload Sizes Chart
  new Chart(document.getElementById('payloadChart'), {{
    type: 'bar',
    data: {{
      labels: chartLabels,
      datasets: [{{
        label: 'Payload Size (MB)',
        data: payloadData,
        backgroundColor: '#f59e0b',
        borderRadius: 4
      }}]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      plugins: {{
        legend: {{ display: false }}
      }},
      scales: {{
        y: {{
          title: {{ display: true, text: 'File Size (MB)', color: '#94a3b8' }},
          grid: {{ color: '#334155' }},
          ticks: {{ color: '#94a3b8' }}
        }},
        x: {{
          grid: {{ display: false }},
          ticks: {{ color: '#94a3b8', maxRotation: 45 }}
        }}
      }}
    }}
  }});

  // 5. Table Search & Filter Logic
  function filterTable() {{
    const search = document.getElementById('searchInput').value.toLowerCase();
    const statusF = document.getElementById('statusFilter').value;
    const powerF = document.getElementById('powerFilter').value;
    const rows = document.querySelectorAll('#metricsTable tbody tr');

    rows.forEach(row => {{
      const text = row.innerText.toLowerCase();
      const status = row.querySelector('td:nth-child(3)').innerText;
      const power = row.querySelector('td:nth-child(4)').innerText;

      const matchesSearch = text.includes(search);
      const matchesStatus = (statusF === 'ALL' || status.includes(statusF));
      const matchesPower = (powerF === 'ALL' || power.includes(powerF));

      if (matchesSearch && matchesStatus && matchesPower) {{
        row.style.display = '';
      }} else {{
        row.style.display = 'none';
      }}
    }});
  }}
</script>
</body>
</html>
"""

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    logger.info(f"Generated interactive dashboard: {output_path}")
    return output_path


def generate_dashboard_from_dir(
    recordings_dir: Optional[str] = None,
    output_path: Optional[str] = None,
    open_browser: bool = False
) -> str:
    """Convenience helper to find lifecycle.log in a directory and produce the dashboard."""
    active_dir = os.path.abspath(recordings_dir) if recordings_dir else DEFAULT_RECORDINGS_DIR
    log_candidates = [
        os.path.join(active_dir, DEFAULT_LOG_NAME),
        os.path.join(REPO_ROOT, DEFAULT_LOG_NAME),
        "/boot/firmware/lifecycle.log",
        "/boot/lifecycle.log",
    ]

    log_path = None
    for cand in log_candidates:
        if os.path.exists(cand):
            log_path = cand
            break

    if not log_path:
        log_path = os.path.join(active_dir, DEFAULT_LOG_NAME)

    target_output = output_path or os.path.join(active_dir, DEFAULT_OUTPUT_NAME)
    records = parse_lifecycle_log(log_path)
    generated = generate_html_dashboard(records, active_dir, target_output)

    if open_browser:
        webbrowser.open(f"file://{os.path.abspath(generated)}")

    return generated


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate interactive HTML visualization dashboard for Wildlife Feeder metrics."
    )
    parser.add_argument(
        "--log",
        type=str,
        default=None,
        help="Path to lifecycle.log CSV file (default: Wild_Life_Recordings/lifecycle.log)"
    )
    parser.add_argument(
        "--recordings-dir", "-d",
        type=str,
        default=DEFAULT_RECORDINGS_DIR,
        help="Path to Wild_Life_Recordings directory"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Target output path for dashboard HTML file"
    )
    parser.add_argument(
        "--open",
        action="store_true",
        default=False,
        help="Open dashboard in default web browser upon completion"
    )
    parser.add_argument(
        "--no-open",
        dest="open",
        action="store_false",
        help="Do not open dashboard in browser"
    )

    args = parser.parse_args(argv)

    rec_dir = os.path.abspath(args.recordings_dir)
    log_path = os.path.abspath(args.log) if args.log else os.path.join(rec_dir, DEFAULT_LOG_NAME)
    out_path = os.path.abspath(args.output) if args.output else os.path.join(rec_dir, DEFAULT_OUTPUT_NAME)

    records = parse_lifecycle_log(log_path)
    generate_html_dashboard(records, rec_dir, out_path)

    if args.open:
        webbrowser.open(f"file://{out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
