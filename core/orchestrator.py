"""
core/orchestrator.py — MacCare Multi-Agent Orchestrator
Implements the ReAct (Reason → Act → Observe → Reflect) loop using Gemma 4 via Ollama.

Architecture:
  - Supervisor Agent   : Interprets user intent, selects tools, synthesises answers
  - Storage Agent      : Handles all disk/file/cache queries
  - Memory Agent       : Handles RAM, CPU, process queries
  - System Agent       : Handles battery, uptime, system info queries
  - Safety Auditor     : Cross-checks every agent action vs. knowledge base
"""

import json
import logging
import re
import time
from typing import Any, Optional

from core.safety_audit import SafetyAuditor

# ── Tool imports ─────────────────────────────────────────────────────────────
from tools.storage import (
    get_disk_usage,
    get_largest_folders,
    get_cache_info,
    get_safe_to_delete,
    find_large_files,
)
from tools.memory import (
    get_memory_usage,
    get_top_memory_processes,
    get_top_cpu_processes,
    get_cpu_usage,
)
from tools.system import (
    get_battery_info,
    get_battery_consuming_processes,
    get_system_info,
    get_running_processes_summary,
)

logger = logging.getLogger("maccare.orchestrator")

# ─────────────────────────────────────────────────────────────────────────────
# Tool Registry — every tool the supervisor can call
# ─────────────────────────────────────────────────────────────────────────────
TOOL_REGISTRY: dict[str, dict] = {
    "get_disk_usage": {
        "fn": get_disk_usage,
        "agent": "StorageAgent",
        "description": "Get total, used, and free disk space with health status.",
        "args": {},
    },
    "get_largest_folders": {
        "fn": get_largest_folders,
        "agent": "StorageAgent",
        "description": "List the largest folders in a given path (default: root). Args: path (str), top_n (int).",
        "args": {"path": "/", "top_n": 10},
    },
    "get_cache_info": {
        "fn": get_cache_info,
        "agent": "StorageAgent",
        "description": "Scan all known cache directories and return sizes.",
        "args": {},
    },
    "get_safe_to_delete": {
        "fn": get_safe_to_delete,
        "agent": "StorageAgent",
        "description": "Find all files/folders safe to delete with their sizes and deletion commands.",
        "args": {},
    },
    "find_large_files": {
        "fn": find_large_files,
        "agent": "StorageAgent",
        "description": "Find large individual files. Args: path (str, default '~'), min_size_mb (int, default 100).",
        "args": {"path": "~", "min_size_mb": 100, "top_n": 10},
    },
    "get_memory_usage": {
        "fn": get_memory_usage,
        "agent": "MemoryAgent",
        "description": "Get RAM usage: total, used, available, swap, and memory pressure.",
        "args": {},
    },
    "get_top_memory_processes": {
        "fn": get_top_memory_processes,
        "agent": "MemoryAgent",
        "description": "List top processes consuming the most RAM. Args: top_n (int, default 10).",
        "args": {"top_n": 10},
    },
    "get_top_cpu_processes": {
        "fn": get_top_cpu_processes,
        "agent": "MemoryAgent",
        "description": "List top processes consuming the most CPU. Args: top_n (int, default 10).",
        "args": {"top_n": 10},
    },
    "get_cpu_usage": {
        "fn": get_cpu_usage,
        "agent": "MemoryAgent",
        "description": "Get overall CPU usage percentage, core count, and per-core breakdown.",
        "args": {},
    },
    "get_battery_info": {
        "fn": get_battery_info,
        "agent": "SystemAgent",
        "description": "Get battery percentage, charging status, cycle count, and health condition.",
        "args": {},
    },
    "get_battery_consuming_processes": {
        "fn": get_battery_consuming_processes,
        "agent": "SystemAgent",
        "description": "Get top battery-draining processes (ranked by CPU usage as a proxy).",
        "args": {"top_n": 10},
    },
    "get_system_info": {
        "fn": get_system_info,
        "agent": "SystemAgent",
        "description": "Get macOS version, hostname, chip model, RAM, and uptime.",
        "args": {},
    },
    "get_running_processes_summary": {
        "fn": get_running_processes_summary,
        "agent": "SystemAgent",
        "description": "Get total running, sleeping, and all process counts.",
        "args": {},
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Tool Schema for LLM function calling
# ─────────────────────────────────────────────────────────────────────────────
def _build_tool_schema() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": info["description"],
                "parameters": {
                    "type": "object",
                    "properties": {
                        k: {"type": "string" if isinstance(v, str) else "integer", "description": f"Default: {v}"}
                        for k, v in info["args"].items()
                    },
                    "required": [],
                },
            },
        }
        for name, info in TOOL_REGISTRY.items()
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Individual Agent Executors
# ─────────────────────────────────────────────────────────────────────────────
class StorageAgent:
    """Handles all disk / file / cache operations."""

    def __init__(self, auditor: SafetyAuditor):
        self.auditor = auditor

    def run(self, tool_name: str, args: dict) -> dict[str, Any]:
        logger.info("[StorageAgent] → %s(%s)", tool_name, args)
        allowed = TOOL_REGISTRY[tool_name].get("args", {}).keys()
        clean_args = {k: v for k, v in args.items() if k in allowed} if args else {}
        fn = TOOL_REGISTRY[tool_name]["fn"]
        result = fn(**clean_args)
        # Post-process: attach health evaluation for disk usage
        if tool_name == "get_disk_usage" and result.get("status") == "ok":
            result["health_evaluation"] = self.auditor.evaluate_disk_health(
                result.get("used_percent", 0)
            )
        return result


class MemoryAgent:
    """Handles RAM, CPU, and process queries."""

    def __init__(self, auditor: SafetyAuditor):
        self.auditor = auditor

    def run(self, tool_name: str, args: dict) -> dict[str, Any]:
        logger.info("[MemoryAgent] → %s(%s)", tool_name, args)
        allowed = TOOL_REGISTRY[tool_name].get("args", {}).keys()
        clean_args = {k: v for k, v in args.items() if k in allowed} if args else {}
        fn = TOOL_REGISTRY[tool_name]["fn"]
        result = fn(**clean_args)
        # Post-process: attach health evaluation for memory
        if tool_name == "get_memory_usage" and result.get("status") == "ok":
            result["health_evaluation"] = self.auditor.evaluate_memory_health(
                result.get("used_percent", 0),
                result.get("memory_pressure", "unknown"),
            )
        return result


class SystemAgent:
    """Handles battery, thermals, uptime, and system info."""

    def __init__(self, auditor: SafetyAuditor):
        self.auditor = auditor

    def run(self, tool_name: str, args: dict) -> dict[str, Any]:
        logger.info("[SystemAgent] → %s(%s)", tool_name, args)
        allowed = TOOL_REGISTRY[tool_name].get("args", {}).keys()
        clean_args = {k: v for k, v in args.items() if k in allowed} if args else {}
        fn = TOOL_REGISTRY[tool_name]["fn"]
        result = fn(**clean_args)
        # Post-process: attach health evaluation for battery
        if tool_name == "get_battery_info" and result.get("status") == "ok":
            result["health_evaluation"] = self.auditor.evaluate_battery_health(
                result.get("cycle_count"),
                result.get("max_capacity_percent"),
                result.get("condition"),
            )
        return result


# ─────────────────────────────────────────────────────────────────────────────
# Supervisor Orchestrator — the main ReAct loop
# ─────────────────────────────────────────────────────────────────────────────
class MacCareOrchestrator:
    """
    Supervisor agent that:
    1. Takes the user's message
    2. Calls Gemma 4 via Ollama to determine which tools to call
    3. Dispatches tool calls to the appropriate sub-agent
    4. Feeds results back to Gemma 4 for synthesis
    5. Returns the final formatted answer
    """

    MODEL = "llama3.2"            # Ollama model name (llama3.2 = Llama 3.2)
    MAX_REACT_STEPS = 6        # max tool calls per query
    OLLAMA_TIMEOUT = 120       # seconds

    def __init__(self):
        self.auditor = SafetyAuditor()
        self.storage_agent = StorageAgent(self.auditor)
        self.memory_agent = MemoryAgent(self.auditor)
        self.system_agent = SystemAgent(self.auditor)
        self._tool_schema = _build_tool_schema()
        self._session_log: list[dict] = []

    # ── Agent router ─────────────────────────────────────────────────────────
    def _dispatch_tool(self, tool_name: str, args: dict) -> dict[str, Any]:
        """Route a tool call to the correct sub-agent."""
        if tool_name not in TOOL_REGISTRY:
            return {"status": "error", "error": f"Unknown tool: {tool_name}"}

        agent_name = TOOL_REGISTRY[tool_name]["agent"]

        if agent_name == "StorageAgent":
            return self.storage_agent.run(tool_name, args)
        elif agent_name == "MemoryAgent":
            return self.memory_agent.run(tool_name, args)
        elif agent_name == "SystemAgent":
            return self.system_agent.run(tool_name, args)

        return {"status": "error", "error": f"No agent for: {agent_name}"}

    # ── Ollama call ──────────────────────────────────────────────────────────
    def _call_ollama(self, messages: list[dict], tools: Optional[list] = None) -> dict:
        """
        Call the Ollama API with the given messages.
        Returns the raw response dict.
        """
        try:
            import ollama
            kwargs: dict[str, Any] = {
                "model": self.MODEL,
                "messages": messages,
                "stream": False,
            }
            if tools:
                kwargs["tools"] = tools

            response = ollama.chat(**kwargs)
            return response
        except Exception as e:
            logger.error("Ollama call failed: %s", e)
            raise

    # ── ReAct loop ────────────────────────────────────────────────────────────
    def run(self, user_message: str) -> str:
        """
        Main entry point. Executes the full ReAct loop for a user query.
        Returns the final answer string.
        """
        logger.info("[Supervisor] User query: %s", user_message)

        # Build conversation with policy-enriched system prompt
        system_prompt = self.auditor.get_system_prompt_context()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        tool_observations: list[str] = []
        steps_taken = 0

        # ── ReAct iterations ──────────────────────────────────────────────────
        while steps_taken < self.MAX_REACT_STEPS:
            steps_taken += 1
            logger.info("[Supervisor] ReAct step %d", steps_taken)

            try:
                response = self._call_ollama(messages, tools=self._tool_schema)
            except Exception as e:
                return f"❌ Error connecting to Ollama: {e}\n\nMake sure Ollama is running: `ollama serve`"

            msg = response.get("message", {})
            tool_calls = msg.get("tool_calls", [])

            # ── No tool calls → synthesise final answer ───────────────────────
            if not tool_calls:
                content = msg.get("content", "")
                logger.info("[Supervisor] Final answer generated.")
                self._log_session(user_message, tool_observations, content)
                return content

            # ── Process each tool call ────────────────────────────────────────
            # Add assistant message with tool calls to history
            messages.append({"role": "assistant", "content": msg.get("content", ""), "tool_calls": tool_calls})

            for tc in tool_calls:
                fn_info = tc.get("function", {})
                tool_name = fn_info.get("name", "")
                raw_args = fn_info.get("arguments", {})

                # Parse args (may be JSON string or dict)
                if isinstance(raw_args, str):
                    try:
                        args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        args = {}
                else:
                    args = raw_args or {}

                logger.info("[Supervisor] Calling tool: %s(%s)", tool_name, args)

                # Safety check for delete-related tools
                if tool_name == "get_safe_to_delete":
                    pass  # safe — read-only
                
                # Execute tool via sub-agent
                t_start = time.time()
                observation = self._dispatch_tool(tool_name, args)
                elapsed = time.time() - t_start

                obs_json = json.dumps(observation, indent=2)[:3000]  # cap length
                obs_summary = f"[Tool: {tool_name} | {elapsed:.1f}s]\n{obs_json}"
                tool_observations.append(obs_summary)

                logger.info("[Supervisor] Tool %s completed in %.1fs", tool_name, elapsed)

                # Feed observation back into messages
                messages.append({
                    "role": "tool",
                    "content": obs_json,
                })

        # Max steps hit — ask LLM to synthesise with what it has
        messages.append({
            "role": "user",
            "content": "Based on all the data you've collected above, please provide your final answer now.",
        })
        try:
            response = self._call_ollama(messages)
            content = response.get("message", {}).get("content", "Unable to generate response.")
        except Exception as e:
            content = f"❌ Error generating final response: {e}"

        self._log_session(user_message, tool_observations, content)
        return content

    # ── Fallback: if Ollama is offline, run rule-based routing ───────────────
    def run_offline(self, user_message: str) -> str:
        """
        Keyword-based fallback for when Ollama is unavailable.
        Runs the most appropriate tools and formats results without LLM synthesis.
        """
        msg = user_message.lower()
        results = []

        if any(w in msg for w in ["storage", "disk", "space", "free", "full"]):
            results.append(("💾 Disk Usage", self.storage_agent.run("get_disk_usage", {})))
            results.append(("📁 Largest Folders", self.storage_agent.run("get_largest_folders", {})))

        if any(w in msg for w in ["folder", "large", "biggest", "directory"]):
            results.append(("📁 Largest Folders", self.storage_agent.run("get_largest_folders", {})))

        if any(w in msg for w in ["cache", "cached", "caches"]):
            results.append(("🗑️ Cache Info", self.storage_agent.run("get_cache_info", {})))

        if any(w in msg for w in ["delete", "clean", "remove", "free up", "junk"]):
            results.append(("🧹 Safe to Delete", self.storage_agent.run("get_safe_to_delete", {})))

        if any(w in msg for w in ["memory", "ram", "swap", "pressure"]):
            results.append(("🧠 Memory Usage", self.memory_agent.run("get_memory_usage", {})))
            results.append(("🧠 Top Memory Processes", self.memory_agent.run("get_top_memory_processes", {})))

        if any(w in msg for w in ["cpu", "processor", "processing"]):
            results.append(("⚡ CPU Usage", self.memory_agent.run("get_cpu_usage", {})))
            results.append(("⚡ Top CPU Processes", self.memory_agent.run("get_top_cpu_processes", {})))

        if any(w in msg for w in ["battery", "charge", "charging", "power"]):
            results.append(("🔋 Battery Info", self.system_agent.run("get_battery_info", {})))
            results.append(("🔋 Battery Draining Apps", self.system_agent.run("get_battery_consuming_processes", {})))

        if any(w in msg for w in ["app", "application", "process", "consuming", "slow", "heavy"]):
            results.append(("⚡ Top CPU Processes", self.memory_agent.run("get_top_cpu_processes", {})))
            results.append(("🧠 Top Memory Processes", self.memory_agent.run("get_top_memory_processes", {})))

        if any(w in msg for w in ["system", "info", "version", "chip", "uptime", "overview", "health"]):
            results.append(("🖥️ System Info", self.system_agent.run("get_system_info", {})))

        if not results:
            # Default: full health overview
            results = [
                ("🖥️ System Info", self.system_agent.run("get_system_info", {})),
                ("💾 Disk Usage", self.storage_agent.run("get_disk_usage", {})),
                ("🧠 Memory", self.memory_agent.run("get_memory_usage", {})),
                ("🔋 Battery", self.system_agent.run("get_battery_info", {})),
            ]

        return json.dumps([{"section": k, "data": v} for k, v in results], indent=2)

    # ── Session logger ────────────────────────────────────────────────────────
    def _log_session(self, query: str, observations: list[str], answer: str):
        import datetime
        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "query": query,
            "tool_calls": len(observations),
            "observations": observations,
            "answer_length": len(answer),
        }
        self._session_log.append(entry)

        # Write to log file
        try:
            from pathlib import Path
            log_dir = Path(__file__).parent.parent / "logs"
            log_dir.mkdir(exist_ok=True)
            log_file = log_dir / "session.log"
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.debug("Log write error: %s", e)
