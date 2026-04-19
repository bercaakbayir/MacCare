"""
core/energy_watchdog.py — Background Battery & Thermal Monitor
Runs in a daemon thread, polls battery/CPU every N seconds,
fires alerts when thresholds are crossed.
"""

import threading
import time
import logging
from typing import Callable, Optional

logger = logging.getLogger("maccare.watchdog")


class EnergyWatchdog:
    """
    Background daemon thread that monitors:
    - Battery percentage (alerts at < 20%)
    - Battery cycle count (alerts at > 800)
    - CPU usage spikes (alerts at > 85% sustained for 30s)
    
    Fires a callback when a threshold is breached.
    Designed to be non-blocking and low-overhead.
    """

    # ── Thresholds ──────────────────────────────
    BATTERY_LOW_PCT      = 20      # % — alert when battery drops below
    BATTERY_CRITICAL_PCT = 10      # % — critical alert
    CPU_SPIKE_PCT        = 85.0    # % — alert when CPU sustained above this
    CPU_SPIKE_DURATION   = 30      # seconds sustained before alerting
    POLL_INTERVAL        = 30      # seconds between polls
    BATTERY_CYCLE_WARN   = 800     # cycle count warning threshold

    def __init__(self, alert_callback: Optional[Callable[[str, str], None]] = None):
        """
        alert_callback(level, message) is called when a threshold is breached.
        level: 'warning' | 'critical'
        """
        self._callback = alert_callback or self._default_callback
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # State tracking
        self._last_battery_alert_pct: Optional[float] = None
        self._cpu_high_since: Optional[float] = None
        self._cpu_spike_alerted = False
        self._cycle_count_alerted = False

    def start(self):
        """Start the watchdog daemon thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="EnergyWatchdog",
            daemon=True,  # dies when main thread exits
        )
        self._thread.start()
        logger.info("⚡ EnergyWatchdog started (poll every %ds)", self.POLL_INTERVAL)

    def stop(self):
        """Signal the watchdog to stop."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("⚡ EnergyWatchdog stopped.")

    # ────────────────────────────────────────────
    # Internal poll loop
    # ────────────────────────────────────────────
    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                self._check_battery()
                self._check_cpu()
            except Exception as e:
                logger.debug("Watchdog poll error: %s", e)
            self._stop_event.wait(timeout=self.POLL_INTERVAL)

    # ────────────────────────────────────────────
    # Battery check
    # ────────────────────────────────────────────
    def _check_battery(self):
        try:
            import psutil
            batt = psutil.sensors_battery()
            if batt is None:
                return  # Desktop Mac — no battery

            pct = batt.percent
            plugged = batt.power_plugged

            if plugged:
                self._last_battery_alert_pct = None  # reset when charging
                return

            if pct <= self.BATTERY_CRITICAL_PCT:
                if self._last_battery_alert_pct != "critical":
                    self._fire("critical",
                        f"🔴 CRITICAL: Battery at {pct:.0f}%! Connect charger immediately.")
                    self._last_battery_alert_pct = "critical"

            elif pct <= self.BATTERY_LOW_PCT:
                if self._last_battery_alert_pct != "low":
                    self._fire("warning",
                        f"🟡 Battery Low: {pct:.0f}% remaining. Consider plugging in.")
                    self._last_battery_alert_pct = "low"
            else:
                self._last_battery_alert_pct = None

            # Check cycle count (once per session)
            if not self._cycle_count_alerted:
                import subprocess, re
                sp = subprocess.run(
                    ["system_profiler", "SPPowerDataType"],
                    capture_output=True, text=True, timeout=10
                )
                m = re.search(r"Cycle Count:\s*(\d+)", sp.stdout)
                if m:
                    cycles = int(m.group(1))
                    if cycles > self.BATTERY_CYCLE_WARN:
                        self._fire("warning",
                            f"🟡 Battery has {cycles} charge cycles (rated ~1000). "
                            "Consider a service check soon.")
                        self._cycle_count_alerted = True

        except ImportError:
            pass
        except Exception as e:
            logger.debug("Battery check error: %s", e)

    # ────────────────────────────────────────────
    # CPU spike check
    # ────────────────────────────────────────────
    def _check_cpu(self):
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=2)

            if cpu >= self.CPU_SPIKE_PCT:
                now = time.time()
                if self._cpu_high_since is None:
                    self._cpu_high_since = now
                    self._cpu_spike_alerted = False

                elapsed = now - self._cpu_high_since
                if elapsed >= self.CPU_SPIKE_DURATION and not self._cpu_spike_alerted:
                    self._fire("warning",
                        f"🟡 CPU Spike: {cpu:.0f}% usage sustained for "
                        f"{int(elapsed)}s. Check for runaway processes.")
                    self._cpu_spike_alerted = True
            else:
                # CPU cooled down — reset
                self._cpu_high_since = None
                self._cpu_spike_alerted = False

        except ImportError:
            pass
        except Exception as e:
            logger.debug("CPU check error: %s", e)

    # ────────────────────────────────────────────
    # Alert dispatcher
    # ────────────────────────────────────────────
    def _fire(self, level: str, message: str):
        logger.warning("[WATCHDOG][%s] %s", level.upper(), message)
        try:
            self._callback(level, message)
        except Exception as e:
            logger.debug("Callback error: %s", e)

    @staticmethod
    def _default_callback(level: str, message: str):
        """Default: print to stderr."""
        import sys
        print(f"\n[⚡ MacCare Watchdog] {message}", file=sys.stderr, flush=True)

    # ────────────────────────────────────────────
    # Status snapshot (call from main thread)
    # ────────────────────────────────────────────
    def get_status(self) -> dict:
        """Return current watchdog monitoring state."""
        return {
            "running": self._thread.is_alive() if self._thread else False,
            "poll_interval_sec": self.POLL_INTERVAL,
            "battery_low_threshold_pct": self.BATTERY_LOW_PCT,
            "cpu_spike_threshold_pct": self.CPU_SPIKE_PCT,
            "cpu_spike_alert_after_sec": self.CPU_SPIKE_DURATION,
            "last_battery_alert": self._last_battery_alert_pct,
            "cpu_spike_active": self._cpu_high_since is not None,
        }
