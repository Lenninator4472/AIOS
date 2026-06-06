"""
AI-DOS Kernel v0.1: The Core Loop
Boots the terminal, processes intents through the LLM,
executes commands safely, and handles self-correction.
"""

import importlib.util
import inspect
import json
import os
import sys
from datetime import datetime
from typing import Optional

# Add parent to path so ai_dos.py can import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kernel.llm import get_provider, extract_json
from kernel.executor import execute, needs_confirmation, set_dry_run, is_dry_run
from kernel.memory import ConversationMemory
from kernel.memory_store import FactMemory
from kernel.bus import EventBus
from kernel.service import Service
from kernel.scheduler import BackgroundTaskScheduler, TaskStatus
from kernel.vfs import VirtualFileSystem
from kernel.agent import Agent, AgentOrchestrator, CODER_PROMPT, RESEARCHER_PROMPT, SYSADMIN_PROMPT, PLANNER_PROMPT
from kernel.checkpoint import save_checkpoint, load_checkpoint

# Rich UI components
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table
from rich.syntax import Syntax
from rich.text import Text
from rich import box

console = Console()

HOME = os.path.expanduser("~")
BASE_DIR = os.path.join(HOME, ".ai-dos")
TOOLS_DIR = os.path.join(BASE_DIR, "tools")
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
SESSION_FILE = os.path.join(SESSIONS_DIR, "last_session.json")
MAX_CONTEXT_CHARS = 60000
MAX_TOOL_DEPTH = 10

# Built-in tool definitions the LLM can invoke directly
TOOLS = {}


def build_tool_definitions() -> str:
    """Build a TOOL_DEFINITIONS string from registered plugin tools."""
    if not TOOLS:
        return ""
    lines = ["\n\nAVAILABLE PLUGIN TOOLS:"]
    for name, func in sorted(TOOLS.items()):
        doc = (func.__doc__ or "No description").strip()
        sig = inspect.signature(func)
        params = []
        for p_name, p_param in sig.parameters.items():
            if p_param.default is not inspect.Parameter.empty:
                params.append(f"{p_name}={p_param.default}")
            else:
                params.append(p_name)
        sig_str = f"tool_{name}({', '.join(params)})"
        lines.append(f"  {sig_str}")
        lines.append(f"    {doc}")
    lines.append('')
    lines.append('To call a tool, include a "tool_calls" field in your JSON:')
    lines.append('[{"name": "tool_name", "arguments": {"arg1": "value1"}}]')
    return "\n".join(lines)

SYSTEM_PROMPT = """You are the Core Intelligence Kernel of an experimental operating system named AI-DOS. You sit directly between the user's natural language desires and a low-level Linux backbone. Your job is to translate human intent into flawless, safe, and efficient system-level actions.

You have root-level execution privileges via a background Python orchestrator. You do not just talk about actions; you perform them. To interact with the hardware and file system, you output raw Bash commands that the orchestrator will immediately run.

OUTPUT FORMAT:
You must respond with ONLY a valid JSON object. No markdown wrapping, no code fences, no extra text.

{
  "thought_process": "Briefly state what the user wants and your plan of execution.",
  "required_tools": ["terminal", "network", "filesystem"],
  "tool_calls": [],  // optional: list of plugin tools to invoke
  "commands": ["command_1", "command_2"],
  "user_response": "A clean, natural language update explaining what you are doing or displaying the final result."
}

CRITICAL RULES:
- SELF-CORRECTION: If a command fails, analyze the error and generate a corrective command.
- DESTRUCTIVE COMMANDS: If the user asks to delete critical system files, pause execution and ask for manual user confirmation in the "user_response" block.
- EFFICIENCY: Combine commands whenever possible to reduce system overhead.
- PLUGIN TOOLS: Use the tool_calls field to invoke plugin tools instead of shell commands when available.
- If the user request is just a question, leave the "commands" list empty.
- Output ONLY valid JSON. No other text. I repeat: ONLY valid JSON."""


def load_plugins():
    """Scan ~/.ai-dos/tools/*.py and register tool_* functions into TOOLS dict."""
    os.makedirs(TOOLS_DIR, exist_ok=True)
    count = 0
    for fname in sorted(os.listdir(TOOLS_DIR)):
        if not fname.endswith(".py"):
            continue
        fpath = os.path.join(TOOLS_DIR, fname)
        mod_name = fname[:-3]
        try:
            spec = importlib.util.spec_from_file_location(mod_name, fpath)
            if spec is None or spec.loader is None:
                console.print(f"  [dim][plugin] skipped {fname}: bad spec[/dim]")
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            found = 0
            for name, func in inspect.getmembers(mod, inspect.isfunction):
                if name.startswith("tool_"):
                    TOOLS[name[5:]] = func
                    found += 1
            if found > 0:
                console.print(f"  [dim][plugin] loaded {fname} ({found} tool(s))[/dim]")
                count += found
            else:
                console.print(f"  [dim][plugin] loaded {fname} (no tool_ functions)[/dim]")
        except Exception as e:
            console.print(f"  [yellow][plugin] error loading {fname}: {e}[/yellow]")
    if count > 0:
        console.print(f"  [dim][plugins] {count} plugin tool(s) available[/dim]")
    return count


def prune_context(messages):
    """Drop oldest user/assistant pairs if total JSON size exceeds limit."""
    total = sum(len(json.dumps(m)) for m in messages)
    if total <= MAX_CONTEXT_CHARS:
        return
    keep = [messages[0]]
    rest = list(messages[1:])
    pruned = 0
    while len(rest) >= 2 and total > MAX_CONTEXT_CHARS:
        rest.pop(0)
        rest.pop(0)
        pruned += 2
        total = sum(len(json.dumps(m)) for m in keep + rest)
    messages.clear()
    messages.extend(keep + rest)
    console.print(f"  [yellow][pruned {pruned} messages, {len(messages)} remaining][/yellow]")


def save_session(messages):
    """Save non-system messages to last_session.json."""
    if len(messages) <= 1:
        return
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    save = messages[1:]
    with open(SESSION_FILE, "w") as f:
        json.dump(save, f)


def load_session():
    """Load previously saved messages from last_session.json."""
    if not os.path.isfile(SESSION_FILE):
        return None
    try:
        with open(SESSION_FILE) as f:
            msgs = json.load(f)
        if isinstance(msgs, list) and len(msgs) > 0:
            return msgs
    except Exception:
        pass
    return None


def parse_tool_call(text):
    """Parse a TOOL:name {...} line from LLM response."""
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("TOOL:"):
            rest = s[5:].strip()
            try:
                idx = rest.index(" ")
                name = rest[:idx]
                raw = rest[idx:].strip()
                raw = raw.removeprefix("```json").removeprefix("```")
                raw = raw.removesuffix("```").strip()
                args = json.loads(raw)
                return {"name": name, "arguments": args}
            except (ValueError, json.JSONDecodeError):
                pass
    return None


class AIDOSKernel:
    """The AI-DOS kernel orchestrator."""

    def __init__(self, model: str = "llama3.2:1b", dry_run: bool = False):
        self.llm = get_provider(model=model)
        self.memory = ConversationMemory(max_exchanges=10)
        self.memory.initialize_default_account()
        self.max_correction_retries = 3
        self.session_log: list[dict] = []

        load_plugins()
        tool_defs = build_tool_definitions()
        self.system_prompt = SYSTEM_PROMPT + tool_defs
        self.messages = [{"role": "system", "content": self.system_prompt}]
        set_dry_run(dry_run)
        self.dry_run = dry_run
        self.facts = FactMemory()
        self.bus = EventBus()
        self.scheduler = BackgroundTaskScheduler(self.bus)
        self.scheduler.start()
        self._task_log: list[dict] = []
        self.bus.subscribe("task.completed", self._on_task_event)
        self.bus.subscribe("task.failed", self._on_task_event)
        self.bus.subscribe("task.started", self._on_task_event)

        # Virtual filesystem: mount live kernel data
        self.vfs = VirtualFileSystem()
        self.vfs.mount("/memory", reader=lambda: self._format_vfs_memory())
        self.vfs.mount("/profile", reader=lambda: self._format_vfs_profile())
        self.vfs.mount("/tasks", reader=lambda: self._format_vfs_tasks())
        self.vfs.mount("/system/provider", reader=lambda: type(self.llm).__name__)
        self.vfs.mount("/system/model", reader=lambda: getattr(self.llm, "model", "unknown"))
        self.vfs.mount("/system/dry_run", reader=lambda: str(self.dry_run))
        self.vfs.mount("/system/facts_count", reader=lambda: str(self.facts.count()))
        self.vfs.mount("/system/plugins", reader=lambda: ", ".join(sorted(TOOLS.keys())) or "(none)")

        # Multi-agent system
        self.orchestrator = AgentOrchestrator(bus=self.bus)
        self.orchestrator.register(Agent("coder", CODER_PROMPT))
        self.orchestrator.register(Agent("research", RESEARCHER_PROMPT))
        self.orchestrator.register(Agent("sysadmin", SYSADMIN_PROMPT))
        self.orchestrator.register(Agent("planner", PLANNER_PROMPT))
        self.vfs.mount("/system/agents", reader=lambda: ", ".join(self.orchestrator.list_agents()))

        load_checkpoint(self)
        saved = load_session()
        if saved:
            console.print(f"  [dim][restored {len(saved)} messages from last session][/dim]")
            self.messages.extend(saved)

    def _format_vfs_memory(self) -> str:
        facts = self.facts.list_all(limit=5)
        if not facts:
            return "No facts stored."
        lines = [f"#{f['id']}: {f['text']}" for f in facts]
        return "\n".join(lines)

    def _format_vfs_profile(self) -> str:
        p = self.memory.get_profile()
        return "\n".join(f"{k}: {v}" for k, v in p.items())

    def _format_vfs_tasks(self) -> str:
        tasks = self.scheduler.list_tasks()
        if not tasks:
            return "No background tasks."
        lines = []
        for t in tasks:
            lines.append(f"[{t.status.value}] {t.task_id[:8]} {t.command[:50]}")
        return "\n".join(lines)

    def _on_task_event(self, event_type: str, data: dict):
        """Callback for task lifecycle events from the scheduler."""
        self._task_log.append({"event": event_type, "data": data})
        if event_type == "task.completed":
            tid = data.get("task_id", "?")[:8]
            console.print(f"\n  [green]✔ Task {tid} completed[/green]")
        elif event_type == "task.failed":
            tid = data.get("task_id", "?")[:8]
            console.print(f"\n  [red]✗ Task {tid} failed (exit {data.get('exit_code')})[/red]")

    def process_intent(self, user_input: str) -> dict:
        """Process a user command through the LLM and return structured decision."""
        profile = self.memory.get_profile()
        profile_context = f"\n\nCURRENT LOGGED ACCOUNT:\n- User: {profile.get('real_name')} ({profile.get('username')})\n- Access Role: {profile.get('system_role')}\n- Primary Environment: {profile.get('primary_stack')}"
        active_system_prompt = self.system_prompt + profile_context

        full_prompt = self._build_prompt(user_input)

        self.messages.append({"role": "user", "content": user_input})
        self.memory.add("user", user_input)

        prune_context(self.messages)

        raw_response = self.llm.query(active_system_prompt, full_prompt, self.memory.get_context())
        decision = extract_json(raw_response)

        if decision is None:
            console.print(f"[dim]Raw LLM response: {raw_response[:200]}...[/dim]")
            return {
                "thought_process": "Failed to parse LLM response as JSON",
                "required_tools": [],
                "commands": [],
                "user_response": f"⚠ Kernel parse error: LLM returned malformed JSON. Raw: {raw_response[:150]}",
            }

        return decision

    def process_intent_streaming(self, user_input: str) -> dict:
        """Process intent with live token streaming to console.

        Streams the raw LLM response tokens as they arrive, then parses JSON
        and handles tool calls embedded in the response.
        """
        profile = self.memory.get_profile()
        profile_context = f"\n\nCURRENT LOGGED ACCOUNT:\n- User: {profile.get('real_name')} ({profile.get('username')})\n- Access Role: {profile.get('system_role')}\n- Primary Environment: {profile.get('primary_stack')}"
        active_system_prompt = self.system_prompt + profile_context

        full_prompt = self._build_prompt(user_input)

        self.messages.append({"role": "user", "content": user_input})
        self.memory.add("user", user_input)

        prune_context(self.messages)

        console.print("[bold cyan]🧠[/bold cyan] ", end="")
        stream = self.llm.query_stream(active_system_prompt, full_prompt, self.memory.get_context())

        raw_response = ""
        for token in stream:
            raw_response += token
            console.print(token, end="", flush=True)
        console.print()

        # Check for TOOL: calls embedded in the raw response
        tool_call = parse_tool_call(raw_response)
        if tool_call and tool_call["name"] in TOOLS:
            func = TOOLS[tool_call["name"]]
            try:
                result = func(**tool_call["arguments"])
                console.print(f"  [dim]🔧 tool {tool_call['name']} → {result[:200]}[/dim]")
            except Exception as e:
                console.print(f"  [dim][red]🔧 tool {tool_call['name']} error: {e}[/red][/dim]")

        decision = extract_json(raw_response)

        if decision is None:
            console.print(f"[dim]Raw LLM response: {raw_response[:200]}...[/dim]")
            return {
                "thought_process": "Failed to parse LLM response as JSON",
                "required_tools": [],
                "commands": [],
                "user_response": f"⚠ Kernel parse error. Raw: {raw_response[:150]}",
            }

        # Handle tool_calls from JSON decision
        tool_calls = decision.get("tool_calls", [])
        for tc in tool_calls:
            name = tc.get("name", "")
            args = tc.get("arguments", {})
            if name in TOOLS:
                func = TOOLS[name]
                try:
                    result = func(**args)
                    console.print(f"  [dim]🔧 {name} → {str(result)[:200]}[/dim]")
                except Exception as e:
                    console.print(f"  [dim][red]🔧 {name} error: {e}[/red][/dim]")

        return decision

    def _build_prompt(self, user_input: str) -> str:
        """Build the user message with history context."""
        return f"User Intent: {user_input}"

    def execute_with_correction(self, commands: list[str], thought_process: str) -> list[dict]:
        """
        Execute commands with automatic error correction.
        Returns list of execution results.
        """
        results = []

        for i, cmd in enumerate(commands):
            # Safety check: destructive commands
            needs_confirm, reason = needs_confirmation(cmd)
            if needs_confirm:
                console.print(Panel(
                    f"[yellow]⚠ Destructive command detected:[/yellow]\n"
                    f"  [bold]{cmd}[/bold]\n"
                    f"  [dim]Reason: {reason}[/dim]\n"
                    f"[bold]Run this command?[/bold] (y/N): ",
                    title="SECURITY CONFIRMATION",
                    border_style="yellow"
                ))
                try:
                    response = input("> ").strip().lower()
                    if response not in ("y", "yes"):
                        console.print("[dim]Command skipped.[/dim]")
                        results.append({
                            "stdout": "",
                            "stderr": f"SKIPPED by user: {reason}",
                            "exit_code": -2,
                        })
                        continue
                except (KeyboardInterrupt, EOFError):
                    results.append({
                        "stdout": "",
                        "stderr": "SKIPPED: interrupted",
                        "exit_code": -2,
                    })
                    continue

            # Execute the command
            result = execute(cmd)
            results.append(result)

            # Self-correction: if command failed, try to fix
            retries = 0
            while result["exit_code"] != 0 and retries < self.max_correction_retries:
                error_context = (
                    f"The following command FAILED with exit code {result['exit_code']}:\n"
                    f"  $ {cmd}\n"
                    f"  stderr: {result['stderr'][:500]}\n"
                    f"  stdout: {result['stdout'][:200]}\n\n"
                    f"Please provide corrected command(s) to achieve the original intent:\n"
                    f"{thought_process}\n\n"
                    f"Respond with the SAME JSON format, but with FIXED commands."
                )

                console.print(f"[yellow]⚠ Command failed (exit {result['exit_code']}). Attempting auto-correction... (try {retries + 1}/{self.max_correction_retries})[/yellow]")

                fix_response = self.llm.query(self.system_prompt, error_context, self.memory.get_context())
                fix_decision = extract_json(fix_response)

                if fix_decision and "commands" in fix_decision and fix_decision["commands"]:
                    # Execute the corrected commands
                    for fix_cmd in fix_decision["commands"]:
                        if fix_cmd.strip():
                            console.print(f"[bold cyan]Auto-correct:[/bold cyan] {fix_cmd}")
                            result = execute(fix_cmd)
                            if result["exit_code"] == 0:
                                break
                retries += 1

            if result["exit_code"] != 0:
                console.print(f"[red]✗ Command failed after {retries} correction attempts.[/red]")

        return results

    def run_interactive(self):
        """Main interactive REPL loop."""
        self._show_boot_screen()

        # Check LLM availability on startup
        test_decision = self.process_intent("Ping")
        if "error" in test_decision.get("user_response", "").lower():
            console.print(f"[red]{test_decision['user_response']}[/red]")
            console.print("[yellow]Starting in offline mode (commands only, no LLM).[/yellow]")

        try:
            while True:
                try:
                    user_input = self._get_input()
                    if user_input is None:
                        continue
                    if user_input == "":
                        continue

                    # Handle built-in commands
                    if user_input.lower() in ("exit", "quit", "shutdown", "poweroff"):
                        self._show_shutdown()
                        break
                    if user_input.lower() == "clear":
                        os.system("clear")
                        continue
                    if user_input.lower() == "help":
                        self._show_help()
                        continue
                    if user_input.lower().startswith("model "):
                        new_model = user_input[6:].strip()
                        if new_model:
                            self.llm.model = new_model
                            console.print(f"[green]Switched to model: {new_model}[/green]")
                        continue
                    if user_input.lower() in ("dry-run", "dryrun"):
                        self.dry_run = not self.dry_run
                        set_dry_run(self.dry_run)
                        status = "ON" if self.dry_run else "OFF"
                        console.print(f"[yellow]Dry-run mode: {status}[/yellow]")
                        continue
                    if user_input.lower().startswith("bg "):
                        cmd = user_input[3:].strip()
                        if cmd:
                            tid = self.scheduler.schedule(cmd)
                            console.print(f"[green]→ Background task launched: {tid[:8]}[/green]")
                        continue
                    if user_input.lower() in ("jobs", "tasks"):
                        tasks = self.scheduler.list_tasks()
                        if tasks:
                            for t in tasks:
                                status_icon = {"pending": "⏳", "running": "▶", "completed": "✔", "failed": "✗"}
                                icon = status_icon.get(t.status.value, "?")
                                console.print(f"  {icon} [dim]{t.task_id[:8]}[/dim] {t.command[:50]} [dim]({t.status.value})[/dim]")
                        else:
                            console.print("[dim]No background tasks.[/dim]")
                        continue
                    if user_input.lower().startswith("cancel "):
                        tid = user_input[7:].strip()
                        if tid:
                            ok = self.scheduler.cancel(tid)
                            console.print(f"[green]Task cancelled[/green]" if ok else "[yellow]Task not found or not running[/yellow]")
                        continue
                    if user_input.lower().startswith("remember "):
                        text = user_input[9:].strip()
                        if text:
                            fid = self.facts.remember(text)
                            console.print(f"[green]Remembered! (fact #{fid})[/green]")
                        continue
                    if user_input.lower().startswith("recall "):
                        query = user_input[7:].strip()
                        if query:
                            results = self.facts.recall(query)
                            if results:
                                for r in results:
                                    console.print(f"  [dim]#{r['id']}[/dim] {r['text']} [dim](score: {r['score']})[/dim]")
                            else:
                                console.print("[yellow]No matching memories found.[/yellow]")
                        continue
                    if user_input.lower().startswith("cat "):
                        vpath = user_input[4:].strip()
                        if vpath:
                            try:
                                content = self.vfs.read(vpath)
                                console.print(content)
                            except Exception as e:
                                console.print(f"[red]VFS error: {e}[/red]")
                        continue
                    if user_input.lower().startswith("agent "):
                        parts = user_input[6:].strip().split(" ", 1)
                        if len(parts) == 2:
                            agent_name, task = parts
                            agent = self.orchestrator.get(agent_name)
                            if agent:
                                console.print(f"[dim]{agent_name} thinking...[/dim]")
                                result = agent.process(task)
                                resp = result.get("user_response", json.dumps(result))[:500]
                                console.print(Panel(resp, title=f"🤖 {agent_name}", border_style="blue"))
                            else:
                                console.print(f"[red]Unknown agent: {agent_name}. Available: {', '.join(self.orchestrator.list_agents())}[/red]")
                        else:
                            console.print("[yellow]Usage: agent <name> <task>[/yellow]")
                        continue
                    if user_input.lower() in ("agents",):
                        agents = self.orchestrator.list_agents()
                        console.print("[bold]Available agents:[/bold]")
                        for a in agents:
                            console.print(f"  🤖 {a}")
                        continue
                    if user_input.lower() == "vfs":
                        items = self.vfs.listdir("/")
                        console.print("[bold]Virtual Filesystem:[/bold]")
                        for name, is_dir in items:
                            marker = "/" if is_dir else ""
                            console.print(f"  /{name}{marker}")
                        continue
                    if user_input.lower() in ("facts", "memories"):
                        facts = self.facts.list_all()
                        if facts:
                            for f in facts:
                                console.print(f"  [dim]#{f['id']}[/dim] {f['text']}")
                        else:
                            console.print("[dim]No facts stored yet.[/dim]")
                        continue

                    # --- PROCESS INTENT (streaming) ---
                    decision = self.process_intent_streaming(user_input)

                    # Store response in messages + memory
                    self.messages.append({"role": "assistant", "content": json.dumps(decision)})
                    self.memory.add("assistant", json.dumps(decision))

                    # --- DISPLAY THOUGHT PROCESS ---
                    if decision.get("thought_process"):
                        console.print(Panel(
                            f"[italic]{decision['thought_process']}[/italic]",
                            title="🧠 KERNEL THOUGHT",
                            border_style="dim",
                            box=box.ROUNDED,
                        ))

                    # --- DISPLAY TOOLS ---
                    tools = decision.get("required_tools", [])
                    if tools:
                        tool_str = ", ".join(f"[blue]{t}[/blue]" for t in tools)
                        console.print(f"  [dim]Tools: {tool_str}[/dim]")

                    # --- EXECUTE COMMANDS ---
                    commands = decision.get("commands", [])
                    if commands:
                        console.print()
                        console.print(Panel(
                            "\n".join(f"  [bold yellow]$ {c}[/bold yellow]" for c in commands),
                            title="⚡ EXECUTING SYSCALLS",
                            border_style="yellow",
                            box=box.ROUNDED,
                        ))

                        results = self.execute_with_correction(commands, decision.get("thought_process", ""))

                        # Show command outputs
                        for cmd, result in zip(commands, results):
                            if result["stdout"]:
                                console.print(Syntax(
                                    result["stdout"].rstrip(),
                                    "bash",
                                    theme="monokai",
                                    word_wrap=True,
                                ))
                            if result["stderr"]:
                                console.print(f"[red]{result['stderr']}[/red]")
                            if result["exit_code"] == 0 and not result["stdout"] and not result["stderr"]:
                                console.print("[dim]✔ Command completed silently.[/dim]")
                            elif result["exit_code"] == -2:
                                console.print(f"[yellow]⏭ {result['stderr']}[/yellow]")

                    # --- USER RESPONSE ---
                    response_text = decision.get("user_response", "")
                    if response_text:
                        console.print()
                        console.print(Panel(
                            Markdown(response_text) if len(response_text) > 50 else response_text,
                            title="🤖 AI-DOS",
                            border_style="green",
                            box=box.ROUNDED,
                        ))

                    # Log session
                    self.session_log.append({
                        "input": user_input,
                        "decision": decision,
                    })

                except KeyboardInterrupt:
                    console.print("\n[yellow]Interrupted. Press Ctrl+D or type 'exit' to shutdown.[/yellow]")
                    continue

        finally:
            save_session(self.messages)

    def _show_boot_screen(self):
        """Display the AI-DOS boot screen."""
        os.system("clear")
        provider_name = type(self.llm).__name__
        model_name = getattr(self.llm, "model", "unknown")
        dry_status = "🔒 DRY-RUN" if self.dry_run else "🔓 LIVE"
        boot = Panel(
            "[bold cyan]AI-DOS Kernel v0.1[/bold cyan]\n"
            "[dim]Experimental AI Operating System[/dim]\n"
            f"[dim]Backend: {provider_name} ({model_name})[/dim]\n"
            "[dim]This is a Lenninator experience[/dim]\n"
            f"[dim]Plugins: {len(TOOLS)} tool(s) loaded | {dry_status}[/dim]\n\n"
            "[green]Type 'help' for commands. 'exit' to shutdown.[/green]",
            title="🚀 SYSTEM BOOT",
            border_style="cyan",
            box=box.DOUBLE,
        )
        console.print(boot)
        console.print()

    def _show_shutdown(self):
        """Display shutdown message."""
        save_checkpoint(self)
        self.scheduler.stop()
        save_session(self.messages)
        tasks_count = len(self.scheduler.list_tasks())
        console.print(Panel(
            "[bold]Shutting down kernel...[/bold]\n"
            f"[dim]Session commands logged: {len(self.session_log)}[/dim]\n"
            f"[dim]Background tasks tracked: {tasks_count}[/dim]\n"
            f"[dim]Session saved: {len(self.messages)} messages[/dim]",
            title="⏻ POWER OFF",
            border_style="red",
        ))

    def _show_help(self):
        """Display help."""
        help_text = Table(box=box.SIMPLE)
        help_text.add_column("Command", style="cyan")
        help_text.add_column("Description", style="white")
        help_text.add_row("exit / quit / shutdown", "Shut down AI-DOS")
        help_text.add_row("clear", "Clear the terminal")
        help_text.add_row("help", "Show this help")
        help_text.add_row("bg <command>", "Run a command in background (non-blocking)")
        help_text.add_row("jobs / tasks", "List all background tasks")
        help_text.add_row("cancel <id>", "Cancel a running background task")
        help_text.add_row("model <name>", "Switch LLM model (e.g., model llama3.2:3b)")
        help_text.add_row("dry-run", "Toggle dry-run mode (simulate, don't execute)")
        help_text.add_row("vfs", "List virtual filesystem root")
        help_text.add_row("cat <path>", "Read a virtual file (e.g., cat /memory)")
        help_text.add_row("remember <text>", "Store a fact in long-term memory")
        help_text.add_row("recall <query>", "Search long-term memory by keywords")
        help_text.add_row("facts", "List all stored facts")
        help_text.add_row("agents", "List available AI agents")
        help_text.add_row("agent <name> <task>", "Delegate a task to a specific agent")
        help_text.add_row("anything else", "Natural language command for the AI kernel")
        console.print(Panel(help_text, title="📖 AI-DOS HELP"))

    def _get_input(self) -> Optional[str]:
        """Get user input with a styled prompt."""
        try:
            prompt = Text("AI-DOS", style="bold cyan")
            prompt.append(" > ", style="bold white")
            console.print(prompt, end="")
            user_input = input()
            return user_input.strip()
        except EOFError:
            self._show_shutdown()
            return None
        except KeyboardInterrupt:
            return None


def run_ai_dos(model: str = "llama3.2:1b", dry_run: bool = False):
    """Entry point to start the AI-DOS kernel."""
    kernel = AIDOSKernel(model=model, dry_run=dry_run)
    kernel.run_interactive()
