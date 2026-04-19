"""
app.py — MacCare Terminal CLI
Rich-powered interactive terminal loop.
Supports both Ollama (LLM mode) and offline (rule-based) mode.
"""

import os
import sys
import json
import logging
import argparse
import datetime
from pathlib import Path

# ── Rich imports ──────────────────────────────────────────────────────────────
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich.rule import Rule
from rich.prompt import Prompt
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.markup import escape
from rich import box

# ── Internal imports ──────────────────────────────────────────────────────────
from core.orchestrator import MacCareOrchestrator
from core.energy_watchdog import EnergyWatchdog

# ── Logging setup ─────────────────────────────────────────────────────────────
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "session.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("maccare.app")

console = Console()

# ─────────────────────────────────────────────────────────────────────────────
# ASCII Banner
# ─────────────────────────────────────────────────────────────────────────────
BANNER = """
[bold bright_cyan]  ███╗   ███╗ █████╗  ██████╗ ██████╗ █████╗ ██████╗ ███████╗[/bold bright_cyan]
[bold bright_cyan]  ████╗ ████║██╔══██╗██╔════╝██╔════╝██╔══██╗██╔══██╗██╔════╝[/bold bright_cyan]
[bold cyan]  ██╔████╔██║███████║██║     ██║     ███████║██████╔╝█████╗  [/bold cyan]
[bold cyan]  ██║╚██╔╝██║██╔══██║██║     ██║     ██╔══██║██╔══██╗██╔══╝  [/bold cyan]
[bold blue]  ██║ ╚═╝ ██║██║  ██║╚██████╗╚██████╗██║  ██║██║  ██║███████╗[/bold blue]
[bold blue]  ╚═╝     ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝[/bold blue]
"""

SUBTITLE = "[dim]macOS Agentic Health Assistant — Powered by Llama 3.2 via Ollama[/dim]"


# ─────────────────────────────────────────────────────────────────────────────
# Rich Formatters — convert raw JSON tool data to human-readable Rich output
# ─────────────────────────────────────────────────────────────────────────────

def _health_badge(health: str) -> str:
    mapping = {
        "healthy": "[bold green]✅ Healthy[/bold green]",
        "warning": "[bold yellow]⚠️  Warning[/bold yellow]",
        "critical": "[bold red]🔴 Critical[/bold red]",
    }
    return mapping.get(health, f"[dim]{health}[/dim]")


def render_disk_usage(data: dict) -> None:
    if data.get("status") == "error":
        console.print(f"[red]Error:[/red] {data.get('error')}")
        return

    badge = _health_badge(data.get("health", ""))
    used_pct = data.get("used_percent", 0)
    bar_filled = int(used_pct / 5)
    bar_empty = 20 - bar_filled
    color = "red" if used_pct > 90 else "yellow" if used_pct > 80 else "cyan"
    bar = f"[{color}]{'█' * bar_filled}[/{color}][dim]{'░' * bar_empty}[/dim]"

    panel_content = (
        f"  {bar}  [bold]{used_pct}%[/bold] used\n\n"
        f"  📦 [bold]Total:[/bold]  {data.get('total_human', 'N/A')}\n"
        f"  🔴 [bold]Used:[/bold]   {data.get('used_human', 'N/A')}\n"
        f"  🟢 [bold]Free:[/bold]   {data.get('free_human', 'N/A')}\n\n"
        f"  Status: {badge}"
    )

    # Health advice
    health_eval = data.get("health_evaluation", {})
    if health_eval and health_eval.get("level"):
        panel_content += f"\n\n  {health_eval['level']}: {escape(health_eval.get('message', ''))}"

    console.print(Panel(panel_content, title="[bold cyan]💾 Disk Storage[/bold cyan]", border_style="cyan"))


def render_largest_folders(data: dict) -> None:
    if data.get("status") == "error":
        console.print(f"[red]Error:[/red] {data.get('error')}")
        return

    table = Table(
        title=f"📁 Largest Folders in [cyan]{data.get('scanned_path', '/')}[/cyan]",
        box=box.ROUNDED,
        border_style="cyan",
        show_lines=False,
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Path", style="white", no_wrap=False, min_width=30)
    table.add_column("Size", style="bold yellow", justify="right", min_width=10)

    for i, folder in enumerate(data.get("folders", []), 1):
        size = folder.get("size_human", "?")
        path = folder.get("path", "?")
        color = "red" if i == 1 else "yellow" if i <= 3 else "white"
        table.add_row(str(i), f"[{color}]{escape(path)}[/{color}]", size)

    console.print(table)


def render_cache_info(data: dict) -> None:
    if data.get("status") == "error":
        console.print(f"[red]Error:[/red] {data.get('error')}")
        return

    table = Table(
        title=f"🗑️ Cache Directories  [dim](Total: {data.get('total_cache_human', '?')})[/dim]",
        box=box.ROUNDED,
        border_style="yellow",
    )
    table.add_column("Cache Type", style="white", min_width=22)
    table.add_column("Path", style="dim", no_wrap=False)
    table.add_column("Size", style="bold yellow", justify="right", min_width=10)
    table.add_column("Safe to Delete", justify="center", min_width=14)

    for c in data.get("caches", []):
        safe = "✅ Yes" if c.get("safe_to_delete") else "⚠️  Check"
        table.add_row(
            c.get("label", "?"),
            escape(c.get("path", "?")),
            c.get("size_human", "?"),
            f"[green]{safe}[/green]" if "Yes" in safe else f"[yellow]{safe}[/yellow]",
        )

    console.print(table)


def render_safe_to_delete(data: dict) -> None:
    if data.get("status") == "error":
        console.print(f"[red]Error:[/red] {data.get('error')}")
        return

    total = data.get("total_recoverable_human", "?")
    console.print(f"\n[bold green]🧹 Total recoverable space: {total}[/bold green]\n")

    table = Table(
        title="Safe-to-Delete Locations",
        box=box.ROUNDED,
        border_style="green",
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Location", style="white", min_width=22)
    table.add_column("Path", style="dim", no_wrap=False)
    table.add_column("Size", style="bold yellow", justify="right")
    table.add_column("How to Delete", style="cyan")

    for i, item in enumerate(data.get("items", []), 1):
        table.add_row(
            str(i),
            item.get("label", "?"),
            escape(item.get("path", "?")),
            item.get("size_human", "?"),
            escape(item.get("delete_cmd", "?")),
        )

    console.print(table)
    console.print(
        "\n[bold yellow]⚠️  Warning:[/bold yellow] Always review files before deleting. "
        "These commands are suggestions — run them manually.\n"
    )


def render_memory_usage(data: dict) -> None:
    if data.get("status") == "error":
        console.print(f"[red]Error:[/red] {data.get('error')}")
        return

    used_pct = data.get("used_percent", 0)
    pressure = data.get("memory_pressure", "unknown")
    pressure_color = {"green": "green", "yellow": "yellow", "red": "red"}.get(pressure, "dim")
    badge = _health_badge(data.get("health", ""))
    bar_filled = int(used_pct / 5)
    bar_empty = 20 - bar_filled
    color = "red" if used_pct > 90 else "yellow" if used_pct > 75 else "cyan"
    bar = f"[{color}]{'█' * bar_filled}[/{color}][dim]{'░' * bar_empty}[/dim]"

    panel_content = (
        f"  {bar}  [bold]{used_pct}%[/bold] used\n\n"
        f"  🧠 [bold]Total RAM:[/bold]       {data.get('total_human', 'N/A')}\n"
        f"  🔴 [bold]Used:[/bold]            {data.get('used_human', 'N/A')}\n"
        f"  🟢 [bold]Available:[/bold]       {data.get('available_human', 'N/A')}\n"
        f"  💾 [bold]Swap Used:[/bold]       {data.get('swap_used_human', 'N/A')} "
        f"({data.get('swap_used_percent', 0):.0f}%)\n"
        f"  🌡️  [bold]Memory Pressure:[/bold] [{pressure_color}]{pressure.upper()}[/{pressure_color}]\n\n"
        f"  Status: {badge}"
    )

    health_eval = data.get("health_evaluation", {})
    if health_eval and health_eval.get("level"):
        panel_content += f"\n\n  {health_eval['level']}: {escape(health_eval.get('message', ''))}"

    console.print(Panel(panel_content, title="[bold magenta]🧠 Memory (RAM)[/bold magenta]", border_style="magenta"))


def render_process_table(data: dict, title: str, metric_key: str, metric_label: str, color: str) -> None:
    if data.get("status") == "error":
        console.print(f"[red]Error:[/red] {data.get('error')}")
        return

    extra = data.get("total_ram_human", data.get("cpu_count_logical", ""))
    table = Table(
        title=f"{title}  [dim]{f'Total RAM: {extra}' if 'RAM' in title else f'Logical Cores: {extra}'}[/dim]",
        box=box.ROUNDED,
        border_style=color,
    )
    table.add_column("PID", style="dim", width=8)
    table.add_column("Process", style="white", min_width=25)
    table.add_column(metric_label, style=f"bold {color}", justify="right", min_width=12)
    table.add_column("Status", style="dim", min_width=10)

    procs = data.get("processes", [])
    for i, p in enumerate(procs):
        val = p.get(metric_key, 0)
        name = p.get("name", "?")
        pid = str(p.get("pid", "?"))
        status = p.get("status", "?")
        row_color = "red" if i == 0 else "yellow" if i < 3 else "white"
        val_str = (
            p.get("memory_human", f"{val}%")
            if metric_key == "memory_bytes"
            else f"{val}%"
        )
        table.add_row(
            pid,
            f"[{row_color}]{escape(name)}[/{row_color}]",
            val_str,
            status,
        )

    console.print(table)


def render_battery(data: dict) -> None:
    if data.get("status") == "error":
        console.print(f"[red]Error:[/red] {data.get('error')}")
        return

    pct = data.get("percent")
    charging = data.get("charging")
    cycles = data.get("cycle_count")
    condition = data.get("condition", "N/A")
    max_cap = data.get("max_capacity_percent")
    time_rem = data.get("time_remaining_min")
    badge = _health_badge(data.get("health", ""))

    charge_icon = "🔌 Charging" if charging else "🔋 On Battery"
    color = "red" if pct and pct < 20 else "yellow" if pct and pct < 40 else "green"
    if pct is not None:
        bar_filled = int(pct / 5)
        bar_empty = 20 - bar_filled
        bar = f"[{color}]{'█' * bar_filled}[/{color}][dim]{'░' * bar_empty}[/dim]"
    else:
        bar = "[dim]No battery data[/dim]"

    time_str = f"{time_rem} min remaining" if time_rem else "Time N/A"

    panel_content = (
        f"  {bar}  [bold]{pct if pct else 'N/A'}%[/bold]  {charge_icon}\n\n"
        f"  ⏱️  [bold]Time Remaining:[/bold]    {time_str}\n"
        f"  🔄 [bold]Cycle Count:[/bold]       {cycles if cycles else 'N/A'} / ~1000\n"
        f"  📊 [bold]Max Capacity:[/bold]      {max_cap if max_cap else 'N/A'}%\n"
        f"  🩺 [bold]Condition:[/bold]         {condition}\n\n"
        f"  Status: {badge}"
    )

    health_eval = data.get("health_evaluation", {})
    if health_eval and health_eval.get("level"):
        panel_content += f"\n\n  {health_eval['level']}: {escape(health_eval.get('message', ''))}"

    console.print(Panel(panel_content, title="[bold yellow]🔋 Battery Health[/bold yellow]", border_style="yellow"))


def render_system_info(data: dict) -> None:
    if data.get("status") == "error":
        console.print(f"[red]Error:[/red] {data.get('error')}")
        return

    table = Table(box=box.SIMPLE, show_header=False, border_style="blue", padding=(0, 2))
    table.add_column("Key", style="bold dim", min_width=20)
    table.add_column("Value", style="white")

    rows = [
        ("🖥️  Hostname", data.get("hostname", "N/A")),
        ("🍎 macOS Version", data.get("macos_version", "N/A")),
        ("⚙️  Processor / Chip", data.get("processor", "N/A")),
        ("🏗️  Architecture", data.get("architecture", "N/A")),
        ("🧠 RAM", data.get("ram", "N/A")),
        ("⏱️  Uptime", data.get("uptime_human", "N/A")),
    ]
    for k, v in rows:
        table.add_row(k, str(v))

    console.print(Panel(table, title="[bold blue]🖥️  System Overview[/bold blue]", border_style="blue"))


def render_cpu_usage(data: dict) -> None:
    if data.get("status") == "error":
        console.print(f"[red]Error:[/red] {data.get('error')}")
        return

    overall = data.get("overall_percent", 0)
    badge = _health_badge(data.get("health", ""))
    bar_filled = int(overall / 5)
    bar_empty = 20 - bar_filled
    color = "red" if overall > 90 else "yellow" if overall > 75 else "cyan"
    bar = f"[{color}]{'█' * bar_filled}[/{color}][dim]{'░' * bar_empty}[/dim]"

    panel_content = (
        f"  {bar}  [bold]{overall}%[/bold] overall\n\n"
        f"  🔢 [bold]Physical Cores:[/bold]  {data.get('physical_cores', 'N/A')}\n"
        f"  🔢 [bold]Logical Cores:[/bold]   {data.get('logical_cores', 'N/A')}\n"
        f"  ⚡ [bold]Current Freq:[/bold]   {data.get('current_freq_mhz', 'N/A')} MHz\n\n"
        f"  Status: {badge}"
    )
    console.print(Panel(panel_content, title="[bold cyan]⚡ CPU Usage[/bold cyan]", border_style="cyan"))


# ─────────────────────────────────────────────────────────────────────────────
# Offline Response Renderer
# Maps JSON tool output to rich panels when Ollama is offline
# ─────────────────────────────────────────────────────────────────────────────
SECTION_RENDERERS = {
    "get_disk_usage": render_disk_usage,
    "get_largest_folders": render_largest_folders,
    "get_cache_info": render_cache_info,
    "get_safe_to_delete": render_safe_to_delete,
    "get_memory_usage": render_memory_usage,
    "get_top_memory_processes": lambda d: render_process_table(
        d, "🧠 Top Memory-Consuming Processes", "memory_bytes", "RAM Used", "magenta"
    ),
    "get_top_cpu_processes": lambda d: render_process_table(
        d, "⚡ Top CPU-Consuming Processes", "cpu_percent", "CPU %", "cyan"
    ),
    "get_cpu_usage": render_cpu_usage,
    "get_battery_info": render_battery,
    "get_battery_consuming_processes": lambda d: render_process_table(
        d, "🔋 Battery-Draining Processes", "cpu_percent", "CPU %", "yellow"
    ),
    "get_system_info": render_system_info,
}


def render_offline_response(raw_json: str) -> None:
    """Parse JSON from run_offline() and render each section."""
    try:
        sections = json.loads(raw_json)
    except json.JSONDecodeError:
        console.print(raw_json)
        return

    for section in sections:
        label = section.get("section", "")
        data = section.get("data", {})
        tool = data.get("tool", "")

        console.print(Rule(f"[bold]{label}[/bold]", style="dim"))

        renderer = SECTION_RENDERERS.get(tool)
        if renderer:
            renderer(data)
        else:
            console.print_json(json.dumps(data))


# ─────────────────────────────────────────────────────────────────────────────
# LLM Response Renderer (Rich markdown-style)
# ─────────────────────────────────────────────────────────────────────────────
def render_llm_response(text: str) -> None:
    """Display LLM response with light markdown processing."""
    from rich.markdown import Markdown
    console.print(Markdown(text))


# ─────────────────────────────────────────────────────────────────────────────
# Built-in Commands
# ─────────────────────────────────────────────────────────────────────────────
BUILTIN_COMMANDS = {
    "help": "Show available commands and example queries",
    "health": "Run a full system health overview",
    "storage": "Check disk storage usage",
    "memory": "Check RAM and memory usage",
    "battery": "Check battery health and status",
    "cpu": "Check CPU usage",
    "cache": "Scan cache directories",
    "clean": "Show what's safe to delete",
    "top": "Show top resource-consuming apps",
    "sysinfo": "Show system information",
    "watchdog": "Show energy watchdog status",
    "clear": "Clear the terminal screen",
    "exit / quit": "Exit MacCare",
}


def show_help() -> None:
    table = Table(
        title="📖 MacCare Commands & Example Queries",
        box=box.ROUNDED,
        border_style="cyan",
    )
    table.add_column("Command / Query", style="bold cyan", min_width=28)
    table.add_column("Description", style="white")

    for cmd, desc in BUILTIN_COMMANDS.items():
        table.add_row(f"  {cmd}", desc)

    table.add_section()
    examples = [
        ("what is my storage capacity?", "Natural language disk query"),
        ("which app uses the most ram?", "Top memory consumer"),
        ("is my battery healthy?", "Battery health check"),
        ("what files can i safely delete?", "Cleanup suggestions"),
        ("show me the biggest folders", "Largest directories"),
        ("what is eating my cpu?", "CPU hog detection"),
        ("give me a full mac health report", "Complete overview"),
    ]
    for q, desc in examples:
        table.add_row(f"  [dim]\"{q}\"[/dim]", f"[dim]{desc}[/dim]")

    console.print(table)


# ─────────────────────────────────────────────────────────────────────────────
# Watchdog alert callback — prints inline in terminal
# ─────────────────────────────────────────────────────────────────────────────
def watchdog_alert(level: str, message: str) -> None:
    color = "red" if level == "critical" else "yellow"
    console.print(f"\n[bold {color}]⚡ [Watchdog Alert][/bold {color}] {message}\n")


# ─────────────────────────────────────────────────────────────────────────────
# Check if Ollama is available
# ─────────────────────────────────────────────────────────────────────────────
def check_ollama_available(model: str = "llama3.2") -> bool:
    try:
        import ollama
        models = ollama.list()
        model_names = [m.get("name", m.get("model", "")) for m in (models.get("models") or [])]
        return any(model in name for name in model_names)
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Main CLI loop
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="MacCare — macOS Agentic Health Assistant")
    parser.add_argument(
        "--offline", action="store_true",
        help="Force offline / rule-based mode (no LLM required)"
    )
    parser.add_argument(
        "--model", default="llama3.2",
        help="Ollama model to use (default: llama3.2)"
    )
    parser.add_argument(
        "--no-watchdog", action="store_true",
        help="Disable background energy watchdog"
    )
    args = parser.parse_args()

    # ── Banner ────────────────────────────────────────────────────────────────
    console.clear()
    console.print(BANNER)
    console.print(SUBTITLE, justify="center")
    console.print()

    # ── Mode detection ────────────────────────────────────────────────────────
    if args.offline:
        ollama_available = False
        console.print(Panel(
            "[bold yellow]⚡ Running in OFFLINE mode[/bold yellow] — rule-based engine active.\n"
            "Responses are powered by direct system tool calls without LLM synthesis.",
            border_style="yellow",
        ))
    else:
        with Progress(SpinnerColumn(), TextColumn("[cyan]Checking Ollama connection..."), transient=True) as prog:
            task = prog.add_task("", total=None)
            ollama_available = check_ollama_available(args.model)
            prog.update(task, completed=True)

        if ollama_available:
            console.print(Panel(
                f"[bold green]✅ Ollama connected[/bold green] — model [cyan]{args.model}[/cyan] ready.\n"
                "MacCare will use the full LLM-powered ReAct agent.",
                border_style="green",
            ))
        else:
            console.print(Panel(
                f"[bold yellow]⚠️  Ollama not found or model [cyan]{args.model}[/cyan] not pulled.[/bold yellow]\n"
                "Falling back to [bold]OFFLINE mode[/bold] (rule-based, no LLM).\n\n"
                "To enable LLM mode:\n"
                "  [cyan]1. Install Ollama:[/cyan] https://ollama.com\n"
                f"  [cyan]2. Pull model:[/cyan]  [white]ollama pull {args.model}[/white]\n"
                "  [cyan]3. Start server:[/cyan] [white]ollama serve[/white]",
                border_style="yellow",
            ))

    # ── Init orchestrator ─────────────────────────────────────────────────────
    with Progress(SpinnerColumn(), TextColumn("[cyan]Initializing agents..."), transient=True) as prog:
        task = prog.add_task("", total=None)
        orchestrator = MacCareOrchestrator()
        orchestrator.MODEL = args.model
        prog.update(task, completed=True)

    # ── Start watchdog ────────────────────────────────────────────────────────
    watchdog = None
    if not args.no_watchdog:
        watchdog = EnergyWatchdog(alert_callback=watchdog_alert)
        watchdog.start()
        console.print("[dim]⚡ Energy watchdog started (background monitoring active)[/dim]\n")

    console.print(Rule("[dim]Type [bold]help[/bold] for commands or ask anything in natural language[/dim]"))
    console.print()

    # ── Main prompt loop ──────────────────────────────────────────────────────
    while True:
        try:
            user_input = Prompt.ask("[bold bright_cyan]maccare[/bold bright_cyan]").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not user_input:
            continue

        cmd = user_input.lower()

        # ── Built-in shortcuts ────────────────────────────────────────────────
        if cmd in ("exit", "quit", "q"):
            break

        elif cmd == "clear":
            console.clear()
            console.print(BANNER)
            continue

        elif cmd == "help":
            show_help()
            continue

        elif cmd == "watchdog":
            if watchdog:
                st = watchdog.get_status()
                console.print_json(json.dumps(st, indent=2))
            else:
                console.print("[dim]Watchdog is disabled.[/dim]")
            continue

        # ── Shortcut commands → natural language expansion ─────────────────
        shortcut_map = {
            "health":   "Give me a complete Mac health overview including storage, memory, battery and CPU",
            "storage":  "What is my current storage usage?",
            "memory":   "What is my current RAM and memory usage?",
            "battery":  "What is the health and status of my battery?",
            "cpu":      "What is my current CPU usage?",
            "cache":    "What cache files exist on my Mac and how large are they?",
            "clean":    "What files are safe to delete on my Mac?",
            "top":      "Which applications are consuming the most memory, CPU and battery?",
            "sysinfo":  "Give me a system information overview of my Mac",
        }
        if cmd in shortcut_map:
            user_input = shortcut_map[cmd]

        # ── Process query ─────────────────────────────────────────────────────
        console.print()
        with Progress(
            SpinnerColumn(),
            TextColumn(f"[cyan]MacCare agents are working on: [white]{user_input[:60]}...[/white][/cyan]"),
            transient=True,
        ) as prog:
            task = prog.add_task("", total=None)

            if ollama_available:
                try:
                    response = orchestrator.run(user_input)
                    prog.update(task, completed=True)
                    console.print()
                    console.print(Rule("[bold cyan]MacCare[/bold cyan]", style="cyan"))
                    render_llm_response(response)
                except Exception as e:
                    prog.update(task, completed=True)
                    console.print(f"\n[red]LLM error:[/red] {e}")
                    console.print("[yellow]Falling back to offline mode...[/yellow]\n")
                    response = orchestrator.run_offline(user_input)
                    render_offline_response(response)
            else:
                response = orchestrator.run_offline(user_input)
                prog.update(task, completed=True)
                console.print()
                console.print(Rule("[bold cyan]MacCare[/bold cyan]", style="cyan"))
                render_offline_response(response)

        console.print()

    # ── Cleanup ───────────────────────────────────────────────────────────────
    if watchdog:
        watchdog.stop()

    console.print()
    console.print(Panel(
        "[bold cyan]Thank you for using MacCare! 🖥️[/bold cyan]\n"
        "[dim]Your Mac health session has been logged to [white]logs/session.log[/white][/dim]",
        border_style="cyan",
    ))


if __name__ == "__main__":
    main()
