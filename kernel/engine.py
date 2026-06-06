"""
AI-DOS Kernel v0.1: The Core Loop
Boots the terminal, processes intents through the LLM,
executes commands safely, and handles self-correction.
"""

import os
import sys
import json
import shlex
from typing import Optional

# Add parent to path so ai_dos.py can import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kernel.llm import OllamaBackend, extract_json
from kernel.executor import execute, needs_confirmation
from kernel.memory import ConversationMemory

# Rich UI components
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table
from rich.syntax import Syntax
from rich.text import Text
from rich import box

console = Console()

SYSTEM_PROMPT = """You are the Core Intelligence Kernel of an experimental operating system named AI-DOS. You sit directly between the user's natural language desires and a low-level Linux backbone. Your job is to translate human intent into flawless, safe, and efficient system-level actions.

You have root-level execution privileges via a background Python orchestrator. You do not just talk about actions; you perform them. To interact with the hardware and file system, you output raw Bash commands that the orchestrator will immediately run.

OUTPUT FORMAT:
You must respond with ONLY a valid JSON object. No markdown wrapping, no code fences, no extra text.

{
  "thought_process": "Briefly state what the user wants and your plan of execution.",
  "required_tools": ["terminal", "network", "filesystem"],
  "commands": ["command_1", "command_2"],
  "user_response": "A clean, natural language update explaining what you are doing or displaying the final result."
}

CRITICAL RULES:
- SELF-CORRECTION: If a command fails, analyze the error and generate a corrective command.
- DESTRUCTIVE COMMANDS: If the user asks to delete critical system files, pause execution and ask for manual user confirmation in the "user_response" block.
- EFFICIENCY: Combine commands whenever possible to reduce system overhead.
- If the user request is just a question, leave the "commands" list empty.
- Output ONLY valid JSON. No other text. I repeat: ONLY valid JSON."""


class AIDOSKernel:
    """The AI-DOS kernel orchestrator."""

    def __init__(self, model: str = "llama3.2:1b"):
        self.llm = OllamaBackend(model=model)
        self.memory = ConversationMemory(max_exchanges=10)
        self.memory.initialize_default_account()  # <-- ADD THIS LINE
        self.max_correction_retries = 3
        self.session_log: list[dict] = []

    def process_intent(self, user_input: str) -> dict:
        """Process a user command through the LLM and return structured decision."""
        # Fetch persistent account details
        profile = self.memory.get_profile()
        profile_context = f"\n\nCURRENT LOGGED ACCOUNT:\n- User: {profile.get('real_name')} ({profile.get('username')})\n- Access Role: {profile.get('system_role')}\n- Primary Environment: {profile.get('primary_stack')}"

        # Inject details dynamically into the root system rules
        active_system_prompt = SYSTEM_PROMPT + profile_context

        # Build prompt with conversation context
        full_prompt = self._build_prompt(user_input)

        # Query the LLM using the newly updated prompt template
        raw_response = self.llm.query(active_system_prompt, full_prompt, self.memory.get_context())

        # Extract JSON
        decision = extract_json(raw_response)

        if decision is None:
            # LLM didn't return valid JSON; wrap in error
            console.print(f"[dim]Raw LLM response: {raw_response[:200]}...[/dim]")
            return {
                "thought_process": "Failed to parse LLM response as JSON",
                "required_tools": [],
                "commands": [],
                "user_response": f"⚠ Kernel parse error: LLM returned malformed JSON. Raw: {raw_response[:150]}",
            }

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

                fix_response = self.llm.query(SYSTEM_PROMPT, error_context, self.memory.get_context())
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

                # Record in memory
                self.memory.add("user", user_input)

                # --- PROCESS INTENT ---
                with console.status("[bold cyan]🧠 Processing intent...[/bold cyan]"):
                    decision = self.process_intent(user_input)

                # Store response in memory
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

    def _show_boot_screen(self):
        """Display the AI-DOS boot screen."""
        os.system("clear")
        boot = Panel(
            "[bold cyan]AI-DOS Kernel v0.1[/bold cyan]\n"
            "[dim]Experimental AI Operating System[/dim]\n"
            "[dim]LLM Core: llama3.2:1b (local)[/dim]\n"
	    "[dim]This is a Lenninator experience[/dim]\n"
            "[dim]Kernel: Python 3.11 + Ollama[/dim]\n\n"
            "[green]Type 'help' for commands. 'exit' to shutdown.[/green]",
            title="🚀 SYSTEM BOOT",
            border_style="cyan",
            box=box.DOUBLE,
        )
        console.print(boot)
        console.print()

    def _show_shutdown(self):
        """Display shutdown message."""
        console.print(Panel(
            "[bold]Shutting down kernel...[/bold]\n"
            f"[dim]Session commands logged: {len(self.session_log)}[/dim]",
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
        help_text.add_row("model <name>", "Switch LLM model (e.g., model llama3.2:3b)")
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


def run_ai_dos(model: str = "llama3.2:1b"):
    """Entry point to start the AI-DOS kernel."""
    kernel = AIDOSKernel(model=model)
    kernel.run_interactive()
