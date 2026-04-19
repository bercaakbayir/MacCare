# 🖥️ Mac Health Agent (MHA) - Complete Technical Specification
**Version:** 1.1
**Primary LLM:** Gemma 4 (8B) via Ollama
**Framework Recommendation:** Pydantic AI or LangGraph (Python)

---

## 1. MISSION & ARCHITECTURE
The MHA is an autonomous terminal-based agent that monitors macOS system health. It uses a **Supervisor-Worker** architecture.
- **The Supervisor (Gemma 4):** Interprets natural language, plans a sequence of tool calls, and evaluates results.
- **The Tools (Python Workers):** Atomic, stateless functions that execute shell commands and return structured JSON.
- **The Knowledge Base (RAG/Markdown):** Local files that act as "Policy Documents" the agent must read before acting.

---

## 2. DIRECTORY STRUCTURE & FILE MANIFEST
The AI should initialize the project with this exact hierarchy:

```text
/mac-health-agent
├── app.py                  # Entry: Terminal CLI Loop (Rich/Textual)
├── core/
│   ├── orchestrator.py     # Gemma 4 logic, ReAct Loop, Tool selection
│   ├── safety_audit.py     # Logic to cross-check tools vs Knowledge Base
│   └── energy_watchdog.py  # Background thread for battery monitoring
├── tools/
│   ├── storage.py          # Wrapper: df, du, find, mdfind
│   ├── memory.py           # Wrapper: psutil, top, vm_stat
│   └── system.py           # Wrapper: pmset, system_profiler
├── knowledge/
│   ├── instructions.md     # Master Agent personality & behavior rules
│   ├── health_advices.md   # Guidelines for optimal Mac health
│   ├── safe_to_delete.md   # Whitelist of deletable file patterns
│   └── protected_apps.md   # Blacklist of processes the AI cannot kill
├── logs/
│   └── session.log         # Detailed tool-call history & LLM reasoning
└── requirements.txt        # psutil, pydantic, ollama, rich

3. DETAILED TOOL SPECIFICATIONS
A. Storage Tool (storage.py)
Action check_capacity: Return Total, Used, and Free space for / in GB.

Action get_folder_sizes: Calculate top 10 largest folders in a directory using du -sh.

Action find_cache: Scan ~/Library/Caches and /Library/Caches for folders > 500MB.

B. Memory & App Tool (memory.py)
Action top_processes: Return top 10 apps sorted by RAM (%mem) and CPU (%cpu).

Data Structure: Must return: {"name": str, "pid": int, "mem_percent": float, "cpu_percent": float}.

Action kill_process: Execute os.kill(pid, signal.SIGTERM) ONLY after safety audit.

C. Power Tool (system.py)
Action get_power_status: Check pmset -g batt.

Return: Battery %, Source (AC/Battery), State (Charging/Discharging).

4. EMERGENCY PROTOCOL: ENERGY OPTIMIZATION
Context: This is a high-priority background "Skill."

The Watchdog Thread: Runs every 60 seconds.

The Condition: If battery < 20% AND source == 'Battery':

The Logic: - AI calls memory.top_processes.

AI filters out any app in protected_apps.md.

AI identifies "Rogue" high-energy apps (e.g., Chrome Renderers using > 15% CPU).

AI presents a "Critical Energy Warning" to the user with a recommendation to kill these apps.

5. AGENT BEHAVIORAL CONSTRAINTS (For instructions.md)
Context Loading: On every startup, the Agent MUST read all .md files in /knowledge.

Verification Loop: Before any rm or kill command:

Compare target path/process name against safe_to_delete.md or protected_apps.md.

If a match is found in protected_apps, REFUSE the action even if the user insists.

Reasoning: In the terminal, show "Thought: [Analysis]" before "Action: [Command]".

Unit Handling: Always convert raw bytes to human-readable (GB/MB).



6. USER INSTRUCTIONS FOR AI
"Using the blueprint above, generate the tools/ directory first. Ensure each tool uses Python's subprocess or psutil and returns strict JSON. Once tools are verified, implement the orchestrator.py using Gemma 4 8B via the Ollama API."


