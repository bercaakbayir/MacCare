"""
tools/storage.py — Storage Agent Tools
Atomic, stateless functions for disk/storage inspection.
Each function returns structured JSON-serialisable dicts.
"""

import subprocess
import os
import time as _time
import shutil
from pathlib import Path
from typing import Any


def _run(cmd: list[str], timeout: int = 30) -> str:
    """Run a shell command and return stdout as string."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return ""
    except FileNotFoundError:
        return ""


def _humanize(size_bytes: int) -> str:
    """Convert bytes to human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


# ─────────────────────────────────────────────
# Tool 1: Get overall disk usage
# ─────────────────────────────────────────────
def get_disk_usage() -> dict[str, Any]:
    """
    Returns total/used/free disk space for the root volume.
    Uses shutil.disk_usage for reliability.
    """
    try:
        usage = shutil.disk_usage("/")
        pct = (usage.used / usage.total) * 100
        return {
            "tool": "get_disk_usage",
            "status": "ok",
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "total_human": _humanize(usage.total),
            "used_human": _humanize(usage.used),
            "free_human": _humanize(usage.free),
            "used_percent": round(pct, 1),
            "health": "critical" if pct > 90 else "warning" if pct > 80 else "healthy",
        }
    except Exception as e:
        return {"tool": "get_disk_usage", "status": "error", "error": str(e)}


# ─────────────────────────────────────────────
# Tool 2: Largest root-level folders
# ─────────────────────────────────────────────
def get_largest_folders(path: str = "/", top_n: int = 10) -> dict[str, Any]:
    """
    Returns the top_n largest directories under `path`.
    Uses `du -sk` for speed; skips inaccessible dirs.
    """
    # Directories that are either protected or too slow to scan
    SKIP_DIRS = {"/System", "/sys", "/proc", "/dev"}
    MAX_TOTAL_SECS = 45   # overall budget for the entire folder scan
    PER_DIR_SECS   = 8    # per-directory du timeout

    try:
        home = str(Path.home())
        scan_dirs = []

        if path in ("/", "root"):
            # Fixed high-value candidates — fast to scan individually
            candidates = [
                home,
                "/Applications",
                "/private/var",
                "/usr",
            ]
            # Add home subdirs (non-hidden only)
            try:
                for d in Path(home).iterdir():
                    if d.is_dir() and not d.name.startswith("."):
                        candidates.append(str(d))
            except PermissionError:
                pass
            scan_dirs = [d for d in candidates if d not in SKIP_DIRS]
        else:
            expand = os.path.expanduser(path)
            try:
                for d in Path(expand).iterdir():
                    if d.is_dir() and str(d) not in SKIP_DIRS:
                        scan_dirs.append(str(d))
            except PermissionError:
                pass

        results = []
        deadline = _time.time() + MAX_TOTAL_SECS
        for d in scan_dirs:
            if _time.time() > deadline:
                break  # ran out of time — return what we have
            try:
                out = _run(["du", "-skx", d], timeout=PER_DIR_SECS)  # -x = single filesystem
                if out:
                    parts = out.split("\t")
                    if len(parts) >= 2:
                        kb = int(parts[0])
                        results.append({
                            "path": parts[1],
                            "size_bytes": kb * 1024,
                            "size_human": _humanize(kb * 1024),
                        })
            except (ValueError, Exception):
                continue

        results.sort(key=lambda x: x["size_bytes"], reverse=True)
        return {
            "tool": "get_largest_folders",
            "status": "ok",
            "scanned_path": path,
            "folders": results[:top_n],
        }
    except Exception as e:
        return {"tool": "get_largest_folders", "status": "error", "error": str(e)}


# ─────────────────────────────────────────────
# Tool 3: Find cache files / directories
# ─────────────────────────────────────────────
def get_cache_info() -> dict[str, Any]:
    """
    Scans well-known cache locations and returns sizes.
    """
    home = Path.home()
    cache_paths = {
        "User App Caches": home / "Library" / "Caches",
        "System Caches": Path("/Library/Caches"),
        "Xcode DerivedData": home / "Library" / "Developer" / "Xcode" / "DerivedData",
        "Xcode Simulators": home / "Library" / "Developer" / "CoreSimulator" / "Caches",
        "npm Cache": home / ".npm" / "_cacache",
        "pip Cache": home / "Library" / "Caches" / "pip",
        "Homebrew Cache": home / "Library" / "Caches" / "Homebrew",
        "Yarn Cache": home / ".yarn" / "cache",
        "Gradle Cache": home / ".gradle" / "caches",
    }

    entries = []
    total_bytes = 0

    for label, path in cache_paths.items():
        if path.exists():
            try:
                out = _run(["du", "-sk", str(path)], timeout=20)
                if out:
                    kb = int(out.split("\t")[0])
                    size_b = kb * 1024
                    total_bytes += size_b
                    entries.append({
                        "label": label,
                        "path": str(path),
                        "size_bytes": size_b,
                        "size_human": _humanize(size_b),
                        "safe_to_delete": True,
                    })
            except Exception:
                pass

    entries.sort(key=lambda x: x["size_bytes"], reverse=True)
    return {
        "tool": "get_cache_info",
        "status": "ok",
        "total_cache_bytes": total_bytes,
        "total_cache_human": _humanize(total_bytes),
        "caches": entries,
    }


# ─────────────────────────────────────────────
# Tool 4: Find safe-to-delete files
# ─────────────────────────────────────────────
def get_safe_to_delete() -> dict[str, Any]:
    """
    Scans known safe-to-delete locations and returns a list
    with sizes and deletion commands.
    """
    home = Path.home()
    safe_targets = [
        {
            "label": "User App Caches",
            "path": str(home / "Library" / "Caches"),
            "delete_cmd": f"rm -rf ~/Library/Caches/*/",
            "safe": True,
        },
        {
            "label": "Xcode DerivedData",
            "path": str(home / "Library" / "Developer" / "Xcode" / "DerivedData"),
            "delete_cmd": "rm -rf ~/Library/Developer/Xcode/DerivedData/",
            "safe": True,
        },
        {
            "label": "Xcode Simulator Caches",
            "path": str(home / "Library" / "Developer" / "CoreSimulator" / "Caches"),
            "delete_cmd": "xcrun simctl delete unavailable",
            "safe": True,
        },
        {
            "label": "User Logs",
            "path": str(home / "Library" / "Logs"),
            "delete_cmd": "rm -rf ~/Library/Logs/*/",
            "safe": True,
        },
        {
            "label": "Crash Reports",
            "path": str(home / "Library" / "Logs" / "DiagnosticReports"),
            "delete_cmd": "rm -rf ~/Library/Logs/DiagnosticReports/*",
            "safe": True,
        },
        {
            "label": "npm Cache",
            "path": str(home / ".npm" / "_cacache"),
            "delete_cmd": "npm cache clean --force",
            "safe": True,
        },
        {
            "label": "Homebrew Cache",
            "path": str(home / "Library" / "Caches" / "Homebrew"),
            "delete_cmd": "brew cleanup",
            "safe": True,
        },
        {
            "label": "pip Cache",
            "path": str(home / "Library" / "Caches" / "pip"),
            "delete_cmd": "pip cache purge",
            "safe": True,
        },
        {
            "label": "Trash",
            "path": str(home / ".Trash"),
            "delete_cmd": "Empty Trash via Finder (right-click Trash icon)",
            "safe": True,
        },
    ]

    results = []
    total_bytes = 0
    for item in safe_targets:
        p = Path(item["path"])
        if p.exists():
            try:
                out = _run(["du", "-sk", str(p)], timeout=20)
                if out:
                    kb = int(out.split("\t")[0])
                    size_b = kb * 1024
                    total_bytes += size_b
                    results.append({**item, "size_bytes": size_b, "size_human": _humanize(size_b)})
            except Exception:
                pass

    results.sort(key=lambda x: x["size_bytes"], reverse=True)
    return {
        "tool": "get_safe_to_delete",
        "status": "ok",
        "total_recoverable_bytes": total_bytes,
        "total_recoverable_human": _humanize(total_bytes),
        "items": results,
    }


# ─────────────────────────────────────────────
# Tool 5: Large files finder
# ─────────────────────────────────────────────
def find_large_files(path: str = "~", min_size_mb: int = 100, top_n: int = 10) -> dict[str, Any]:
    """
    Finds individual files larger than min_size_mb in the given path.
    """
    expand = os.path.expanduser(path)
    min_bytes = min_size_mb * 1024 * 1024
    
    # Use find command
    min_kb = min_size_mb * 1024
    out = _run(["find", expand, "-type", "f", "-size", f"+{min_kb}k",
                "-not", "-path", "*/.*",  # skip hidden
                "-exec", "du", "-sk", "{}", ";"], timeout=60)
    
    results = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 2:
            try:
                kb = int(parts[0])
                results.append({
                    "path": parts[1],
                    "size_bytes": kb * 1024,
                    "size_human": _humanize(kb * 1024),
                })
            except ValueError:
                pass

    results.sort(key=lambda x: x["size_bytes"], reverse=True)
    return {
        "tool": "find_large_files",
        "status": "ok",
        "search_path": path,
        "min_size_mb": min_size_mb,
        "files": results[:top_n],
    }
