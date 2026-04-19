"""
tools/memory.py — Memory & Process Agent Tools
Atomic, stateless functions for RAM, CPU, and process inspection.
"""

import subprocess
import os
from typing import Any

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


def _humanize(size_bytes: float) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def _run(cmd: list[str], timeout: int = 15) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


# ─────────────────────────────────────────────
# Tool 1: RAM / Memory overview
# ─────────────────────────────────────────────
def get_memory_usage() -> dict[str, Any]:
    """
    Returns total RAM, used, available, swap, and memory pressure.
    """
    if not PSUTIL_AVAILABLE:
        return {"tool": "get_memory_usage", "status": "error", "error": "psutil not installed"}

    try:
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        pct = mem.percent

        # Memory pressure via vm_stat
        pressure = "unknown"
        vm_stat = _run(["vm_stat"])
        if vm_stat:
            lines = vm_stat.splitlines()
            stats = {}
            for line in lines[1:]:
                if ":" in line:
                    k, v = line.split(":", 1)
                    v = v.strip().rstrip(".")
                    try:
                        stats[k.strip()] = int(v)
                    except ValueError:
                        pass
            page_size = 4096
            wired = stats.get("Pages wired down", 0) * page_size
            active = stats.get("Pages active", 0) * page_size
            compressed = stats.get("Pages occupied by compressor", 0) * page_size
            pressure_pct = ((wired + active + compressed) / mem.total) * 100 if mem.total else 0
            pressure = "red" if pressure_pct > 85 else "yellow" if pressure_pct > 70 else "green"

        return {
            "tool": "get_memory_usage",
            "status": "ok",
            "total_bytes": mem.total,
            "total_human": _humanize(mem.total),
            "used_bytes": mem.used,
            "used_human": _humanize(mem.used),
            "available_bytes": mem.available,
            "available_human": _humanize(mem.available),
            "used_percent": pct,
            "swap_total_human": _humanize(swap.total),
            "swap_used_human": _humanize(swap.used),
            "swap_used_percent": swap.percent,
            "memory_pressure": pressure,
            "health": "critical" if pct > 90 or pressure == "red"
                      else "warning" if pct > 75 or pressure == "yellow"
                      else "healthy",
        }
    except Exception as e:
        return {"tool": "get_memory_usage", "status": "error", "error": str(e)}


# ─────────────────────────────────────────────
# Tool 2: Top memory-consuming processes
# ─────────────────────────────────────────────
def get_top_memory_processes(top_n: int = 10) -> dict[str, Any]:
    """
    Returns processes sorted by memory consumption.
    """
    if not PSUTIL_AVAILABLE:
        return {"tool": "get_top_memory_processes", "status": "error", "error": "psutil not installed"}

    try:
        total_mem = psutil.virtual_memory().total
        procs = []
        for proc in psutil.process_iter(["pid", "name", "memory_info", "memory_percent", "status"]):
            try:
                info = proc.info
                rss = info["memory_info"].rss if info["memory_info"] else 0
                procs.append({
                    "pid": info["pid"],
                    "name": info["name"],
                    "memory_bytes": rss,
                    "memory_human": _humanize(rss),
                    "memory_percent": round(info["memory_percent"] or 0, 2),
                    "status": info["status"],
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        procs.sort(key=lambda x: x["memory_bytes"], reverse=True)
        return {
            "tool": "get_top_memory_processes",
            "status": "ok",
            "total_ram_human": _humanize(total_mem),
            "processes": procs[:top_n],
        }
    except Exception as e:
        return {"tool": "get_top_memory_processes", "status": "error", "error": str(e)}


# ─────────────────────────────────────────────
# Tool 3: Top CPU-consuming processes
# ─────────────────────────────────────────────
def get_top_cpu_processes(top_n: int = 10) -> dict[str, Any]:
    """
    Returns processes sorted by CPU usage (1-second sample).
    """
    if not PSUTIL_AVAILABLE:
        return {"tool": "get_top_cpu_processes", "status": "error", "error": "psutil not installed"}

    try:
        # Prime CPU counters
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                proc.cpu_percent(interval=None)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        import time
        time.sleep(1.0)  # 1-second measurement window

        procs = []
        for proc in psutil.process_iter(["pid", "name", "status"]):
            try:
                cpu = proc.cpu_percent(interval=None)
                procs.append({
                    "pid": proc.info["pid"],
                    "name": proc.info["name"],
                    "cpu_percent": round(cpu, 2),
                    "status": proc.info["status"],
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        procs = [p for p in procs if p["cpu_percent"] > 0]
        procs.sort(key=lambda x: x["cpu_percent"], reverse=True)

        cpu_count = psutil.cpu_count(logical=True)
        return {
            "tool": "get_top_cpu_processes",
            "status": "ok",
            "cpu_count_logical": cpu_count,
            "processes": procs[:top_n],
        }
    except Exception as e:
        return {"tool": "get_top_cpu_processes", "status": "error", "error": str(e)}


# ─────────────────────────────────────────────
# Tool 4: Overall CPU usage
# ─────────────────────────────────────────────
def get_cpu_usage() -> dict[str, Any]:
    """
    Returns overall CPU usage percentage and per-core breakdown.
    """
    if not PSUTIL_AVAILABLE:
        return {"tool": "get_cpu_usage", "status": "error", "error": "psutil not installed"}

    try:
        overall = psutil.cpu_percent(interval=1)
        per_core = psutil.cpu_percent(interval=None, percpu=True)
        freq = psutil.cpu_freq()
        count_logical = psutil.cpu_count(logical=True)
        count_physical = psutil.cpu_count(logical=False)

        return {
            "tool": "get_cpu_usage",
            "status": "ok",
            "overall_percent": overall,
            "physical_cores": count_physical,
            "logical_cores": count_logical,
            "current_freq_mhz": round(freq.current, 0) if freq else None,
            "max_freq_mhz": round(freq.max, 0) if freq else None,
            "per_core_percent": per_core,
            "health": "critical" if overall > 90 else "warning" if overall > 75 else "healthy",
        }
    except Exception as e:
        return {"tool": "get_cpu_usage", "status": "error", "error": str(e)}
