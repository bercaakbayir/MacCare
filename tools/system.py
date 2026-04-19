"""
tools/system.py — System & Battery Agent Tools
Atomic, stateless functions for battery, thermals, uptime, and system info.
"""

import subprocess
import platform
import re
from typing import Any

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


def _run(cmd: list[str], timeout: int = 15) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


def _humanize(seconds: float) -> str:
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    mins = int((seconds % 3600) // 60)
    parts = []
    if days: parts.append(f"{days}d")
    if hours: parts.append(f"{hours}h")
    if mins: parts.append(f"{mins}m")
    return " ".join(parts) if parts else "< 1m"


# ─────────────────────────────────────────────
# Tool 1: Battery status
# ─────────────────────────────────────────────
def get_battery_info() -> dict[str, Any]:
    """
    Returns battery percentage, health, cycle count, charging status.
    Uses pmset and system_profiler for macOS.
    """
    result = {
        "tool": "get_battery_info",
        "status": "ok",
        "percent": None,
        "charging": None,
        "cycle_count": None,
        "condition": None,
        "max_capacity_percent": None,
        "time_remaining_min": None,
        "health": "unknown",
    }

    # psutil battery
    if PSUTIL_AVAILABLE:
        try:
            batt = psutil.sensors_battery()
            if batt:
                result["percent"] = round(batt.percent, 1)
                result["charging"] = batt.power_plugged
                secs = batt.secsleft
                if secs and secs > 0:
                    result["time_remaining_min"] = round(secs / 60)
        except Exception:
            pass

    # pmset for detailed info
    pmset = _run(["pmset", "-g", "batt"])
    if pmset:
        # Charging state
        if "charging" in pmset.lower():
            result["charging"] = True
        elif "discharging" in pmset.lower():
            result["charging"] = False
        # Percentage fallback
        pct_match = re.search(r"(\d+)%", pmset)
        if pct_match and result["percent"] is None:
            result["percent"] = int(pct_match.group(1))
        # Time remaining
        time_match = re.search(r"(\d+:\d+) remaining", pmset)
        if time_match:
            h, m = time_match.group(1).split(":")
            result["time_remaining_min"] = int(h) * 60 + int(m)

    # system_profiler for cycle count and health
    sp = _run(["system_profiler", "SPPowerDataType"], timeout=20)
    if sp:
        cycle_match = re.search(r"Cycle Count:\s*(\d+)", sp)
        if cycle_match:
            result["cycle_count"] = int(cycle_match.group(1))

        condition_match = re.search(r"Condition:\s*(.+)", sp)
        if condition_match:
            result["condition"] = condition_match.group(1).strip()

        capacity_match = re.search(r"Maximum Capacity:\s*(\d+)%", sp)
        if capacity_match:
            result["max_capacity_percent"] = int(capacity_match.group(1))

    # Evaluate health
    pct = result.get("percent")
    cycle = result.get("cycle_count")
    max_cap = result.get("max_capacity_percent")
    condition = result.get("condition", "")

    if condition and "service" in condition.lower():
        result["health"] = "critical"
    elif max_cap and max_cap < 80:
        result["health"] = "warning"
    elif cycle and cycle > 800:
        result["health"] = "warning"
    elif pct is not None and pct < 20 and not result.get("charging"):
        result["health"] = "warning"
    else:
        result["health"] = "healthy"

    return result


# ─────────────────────────────────────────────
# Tool 2: Top battery-draining processes
# ─────────────────────────────────────────────
def get_battery_consuming_processes(top_n: int = 10) -> dict[str, Any]:
    """
    Returns processes sorted by CPU (proxy for battery drain).
    Also uses `powermetrics` if available (requires sudo).
    """
    procs = []
    if PSUTIL_AVAILABLE:
        try:
            import time
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    proc.cpu_percent(interval=None)
                except Exception:
                    pass
            time.sleep(1)
            for proc in psutil.process_iter(["pid", "name", "status"]):
                try:
                    cpu = proc.cpu_percent(interval=None)
                    if cpu > 0:
                        procs.append({
                            "pid": proc.info["pid"],
                            "name": proc.info["name"],
                            "cpu_percent": round(cpu, 2),
                        })
                except Exception:
                    pass
            procs.sort(key=lambda x: x["cpu_percent"], reverse=True)
        except Exception as e:
            return {"tool": "get_battery_consuming_processes", "status": "error", "error": str(e)}

    return {
        "tool": "get_battery_consuming_processes",
        "status": "ok",
        "note": "Battery drain estimated from CPU usage. Higher CPU = more battery drain.",
        "processes": procs[:top_n],
    }


# ─────────────────────────────────────────────
# Tool 3: System overview
# ─────────────────────────────────────────────
def get_system_info() -> dict[str, Any]:
    """
    Returns macOS version, hostname, uptime, CPU model, RAM.
    """
    try:
        uptime_sec = None
        if PSUTIL_AVAILABLE:
            import time as t
            boot = psutil.boot_time()
            uptime_sec = t.time() - boot

        mac_ver = platform.mac_ver()[0]
        machine = platform.machine()
        node = platform.node()
        processor = platform.processor()

        # System profiler for hardware overview
        hw = _run(["system_profiler", "SPHardwareDataType"], timeout=15)
        chip = None
        ram_str = None
        if hw:
            chip_match = re.search(r"Chip:\s*(.+)", hw)
            if chip_match:
                chip = chip_match.group(1).strip()
            mem_match = re.search(r"Memory:\s*(.+)", hw)
            if mem_match:
                ram_str = mem_match.group(1).strip()

        return {
            "tool": "get_system_info",
            "status": "ok",
            "hostname": node,
            "macos_version": mac_ver,
            "architecture": machine,
            "processor": chip or processor,
            "ram": ram_str,
            "uptime_seconds": uptime_sec,
            "uptime_human": _humanize(uptime_sec) if uptime_sec else "unknown",
        }
    except Exception as e:
        return {"tool": "get_system_info", "status": "error", "error": str(e)}


# ─────────────────────────────────────────────
# Tool 4: Running processes overview
# ─────────────────────────────────────────────
def get_running_processes_summary() -> dict[str, Any]:
    """
    Returns count of running processes and top resource consumers summary.
    """
    if not PSUTIL_AVAILABLE:
        return {"tool": "get_running_processes_summary", "status": "error", "error": "psutil not installed"}

    try:
        total = 0
        running = 0
        sleeping = 0
        for proc in psutil.process_iter(["status"]):
            try:
                total += 1
                s = proc.info["status"]
                if s == psutil.STATUS_RUNNING:
                    running += 1
                elif s == psutil.STATUS_SLEEPING:
                    sleeping += 1
            except Exception:
                pass

        return {
            "tool": "get_running_processes_summary",
            "status": "ok",
            "total_processes": total,
            "running": running,
            "sleeping": sleeping,
        }
    except Exception as e:
        return {"tool": "get_running_processes_summary", "status": "error", "error": str(e)}
