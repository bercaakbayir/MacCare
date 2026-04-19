"""
core/safety_audit.py — Safety & Knowledge Base Auditor
Cross-checks agent actions against the knowledge base Markdown policies.
"""

import re
from pathlib import Path
from typing import Any, Optional

KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"


def _load(filename: str) -> str:
    """Load a knowledge base markdown file."""
    path = KNOWLEDGE_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


class SafetyAuditor:
    """
    Validates agent intentions against the knowledge base policy documents.
    All checks are stateless — call them before executing any destructive action.
    """

    def __init__(self):
        self._safe_to_delete = _load("safe_to_delete.md")
        self._protected_apps = _load("protected_apps.md")
        self._health_advices = _load("health_advices.md")
        self._instructions = _load("instructions.md")

    def reload(self):
        """Reload knowledge base from disk (call if files change at runtime)."""
        self.__init__()

    # ─────────────────────────────────
    # 1. Path deletion safety check
    # ─────────────────────────────────
    def is_path_safe_to_delete(self, path: str) -> dict[str, Any]:
        """
        Returns whether a given path is whitelisted for deletion.
        """
        path_lower = path.lower()
        # Extract all paths from safe_to_delete.md using backtick patterns
        safe_patterns = re.findall(r"`([^`]+)`", self._safe_to_delete)
        # Also extract paths from table rows
        table_paths = re.findall(r"\|\s*(`[^`]+`|~[^\|]+)\s*\|", self._safe_to_delete)

        # Check against pattern list
        for pattern in safe_patterns:
            p = pattern.replace("~", str(Path.home())).lower()
            p = p.rstrip("/").rstrip("*")
            if p in path_lower or path_lower.startswith(p):
                return {
                    "safe": True,
                    "path": path,
                    "matched_pattern": pattern,
                    "source": "safe_to_delete.md",
                }

        # Check for explicitly protected paths
        protected_keywords = [
            "/system/", "/library/preferences/", "/library/keychains/",
            "/library/application support/", "launchd", "loginwindow",
        ]
        for kw in protected_keywords:
            if kw in path_lower:
                return {
                    "safe": False,
                    "path": path,
                    "reason": f"Path matches protected pattern: '{kw}'",
                    "source": "safe_to_delete.md (protected section)",
                }

        return {
            "safe": False,
            "path": path,
            "reason": "Path is not in the approved safe-to-delete whitelist.",
            "source": "safe_to_delete.md",
            "advice": "Only delete this manually after careful review.",
        }

    # ─────────────────────────────────
    # 2. Process kill safety check
    # ─────────────────────────────────
    def is_process_safe_to_kill(self, process_name: str) -> dict[str, Any]:
        """
        Returns whether a process can be safely terminated.
        """
        name_lower = process_name.lower().strip()

        # Extract process names from protected_apps.md table rows
        # Matches lines like: | `kernel_task` | ...
        protected_names = re.findall(r"\|\s*`([^`]+)`\s*\|", self._protected_apps)
        protected_names_lower = [p.lower() for p in protected_names]

        if name_lower in protected_names_lower:
            # Find the description
            pattern = re.compile(
                rf"\|\s*`{re.escape(name_lower)}`\s*\|\s*([^\|]+)\|", re.IGNORECASE
            )
            match = pattern.search(self._protected_apps)
            description = match.group(1).strip() if match else "Critical system process"

            return {
                "safe": False,
                "process": process_name,
                "reason": f"Protected system process: {description}",
                "source": "protected_apps.md",
                "alternative": "Restart the Mac or investigate root cause instead.",
            }

        return {
            "safe": True,
            "process": process_name,
            "note": "Not in protected list. Use caution — verify this process before killing.",
        }

    # ─────────────────────────────────
    # 3. Health threshold advice lookup
    # ─────────────────────────────────
    def get_health_advice(self, topic: str) -> str:
        """
        Returns relevant health advice from health_advices.md for a given topic.
        topic: 'storage' | 'memory' | 'battery' | 'cpu' | 'cache' | 'general'
        """
        topic_lower = topic.lower()
        sections = re.split(r"\n## ", self._health_advices)
        for section in sections:
            if topic_lower in section[:40].lower():
                # Return first 800 chars of matching section
                return section[:800].strip()
        return self._health_advices[:500]

    # ─────────────────────────────────
    # 4. Full knowledge base context
    # ─────────────────────────────────
    def get_system_prompt_context(self) -> str:
        """
        Builds the system prompt enriched with knowledge base context.
        Used by the orchestrator to inject policy into the LLM system prompt.
        """
        return f"""
{self._instructions}

---
## KNOWLEDGE BASE: Health Thresholds
{self._health_advices[:1500]}

---
## KNOWLEDGE BASE: Safe-to-Delete Whitelist (summary)
Only suggest deleting paths from this list. Never deviate.
{self._safe_to_delete[:800]}

---
## KNOWLEDGE BASE: Protected Processes (never kill these)
{self._protected_apps[:600]}
""".strip()

    # ─────────────────────────────────
    # 5. Disk health evaluation
    # ─────────────────────────────────
    def evaluate_disk_health(self, used_percent: float) -> dict[str, Any]:
        if used_percent > 90:
            return {
                "level": "🔴 CRITICAL",
                "message": "Disk is over 90% full. macOS performance will degrade severely.",
                "advice": self.get_health_advice("storage"),
            }
        elif used_percent > 80:
            return {
                "level": "🟡 WARNING",
                "message": "Disk is over 80% full. Time Machine and virtual memory may be affected.",
                "advice": self.get_health_advice("storage"),
            }
        return {
            "level": "✅ HEALTHY",
            "message": f"Disk usage is at {used_percent:.1f}% — within healthy range.",
            "advice": None,
        }

    # ─────────────────────────────────
    # 6. Memory health evaluation
    # ─────────────────────────────────
    def evaluate_memory_health(self, used_percent: float, pressure: str) -> dict[str, Any]:
        if pressure == "red" or used_percent > 90:
            return {
                "level": "🔴 CRITICAL",
                "message": "Memory pressure is critical. System is swapping heavily.",
                "advice": self.get_health_advice("memory"),
            }
        elif pressure == "yellow" or used_percent > 75:
            return {
                "level": "🟡 WARNING",
                "message": "Memory pressure is elevated. Consider closing unused applications.",
                "advice": self.get_health_advice("memory"),
            }
        return {
            "level": "✅ HEALTHY",
            "message": f"RAM usage is {used_percent:.1f}% with {pressure} pressure — healthy.",
            "advice": None,
        }

    # ─────────────────────────────────
    # 7. Battery health evaluation
    # ─────────────────────────────────
    def evaluate_battery_health(self, cycle_count: Optional[int], max_capacity: Optional[int],
                                 condition: Optional[str]) -> dict[str, Any]:
        if condition and "service" in (condition or "").lower():
            return {
                "level": "🔴 CRITICAL",
                "message": f"Battery condition is '{condition}'. Replacement recommended.",
                "advice": self.get_health_advice("battery"),
            }
        if max_capacity and max_capacity < 80:
            return {
                "level": "🟡 WARNING",
                "message": f"Battery maximum capacity is {max_capacity}%. Degraded health.",
                "advice": self.get_health_advice("battery"),
            }
        if cycle_count and cycle_count > 800:
            return {
                "level": "🟡 WARNING",
                "message": f"Battery has {cycle_count} cycles (rated for ~1000). Monitor closely.",
                "advice": self.get_health_advice("battery"),
            }
        return {
            "level": "✅ HEALTHY",
            "message": "Battery health looks good.",
            "advice": None,
        }
