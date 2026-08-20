"""Display layer for streaming agent output in the terminal."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from rich.console import Console
from rich.markup import escape
from rich.syntax import Syntax
from rich.text import Text

from kadmon.providers.base import StreamChunk, StreamEvent

if TYPE_CHECKING:
    from kadmon.agent.context import ContextStats
    from kadmon.agent.loop import UsageSummary

console = Console()


# --- Slash Command Dispatch ---


class SlashAction(Enum):
    """Actions a slash command can request."""

    HELP = "help"
    CLEAR = "clear"
    STATUS = "status"
    CHECKPOINTS = "checkpoints"
    MODEL = "model"
    PROVIDERS = "providers"
    CONTEXT = "context"
    COST = "cost"
    EXIT = "exit"
    UNKNOWN = "unknown"


@dataclass
class SlashResult:
    """Result of dispatching a slash command."""

    action: SlashAction
    message: str = ""


_COMMANDS: dict[str, SlashAction] = {
    "/help": SlashAction.HELP,
    "/clear": SlashAction.CLEAR,
    "/status": SlashAction.STATUS,
    "/checkpoints": SlashAction.CHECKPOINTS,
    "/model": SlashAction.MODEL,
    "/providers": SlashAction.PROVIDERS,
    "/context": SlashAction.CONTEXT,
    "/cost": SlashAction.COST,
    "/exit": SlashAction.EXIT,
    "/quit": SlashAction.EXIT,
}

_HELP_TEXT = """\
Available commands:
  /help         Show this help
  /clear        Reset conversation context
  /status       Show session and library state
  /context      Show context-window budget meter
  /cost         Show token usage and cost estimate
  /checkpoints  List file checkpoints
  /model        Show current provider/model
  /exit, /quit  Exit kadmon"""


def handle_slash_command(cmd: str) -> SlashResult:
    """Dispatch a slash command string to a SlashResult.

    Pure function — no side effects. The caller acts on the result.
    """
    normalized = cmd.strip().lower()
    action = _COMMANDS.get(normalized)
    if action is None:
        return SlashResult(
            action=SlashAction.UNKNOWN,
            message=f"Unknown command: {normalized}. Type /help for available commands.",
        )
    if action == SlashAction.HELP:
        return SlashResult(action=SlashAction.HELP, message=_HELP_TEXT)
    return SlashResult(action=action)


# --- Context & Cost Renderers ---


def render_context_meter(stats: ContextStats, target_console: Console | None = None) -> None:
    """Render a context-budget meter from a ContextStats instance.

    Shows a progress bar, utilization %, token counts, and a warning if near handoff.
    """
    out = target_console or console
    pct = int(stats.utilization * 100)
    bar_width = 30
    filled = min(int(stats.utilization * bar_width), bar_width)
    bar = "█" * filled + "░" * (bar_width - filled)
    color = "red" if stats.near_handoff else ("yellow" if pct >= 60 else "green")
    out.print("\n[bold]Context Budget[/bold]")
    out.print(f"  [{color}]{bar}[/{color}] {pct}%")
    out.print(f"  Tokens: {stats.used_tokens:,} / {stats.max_tokens:,}")
    out.print(f"  Messages: {stats.message_count}")
    if stats.near_handoff:
        out.print("  [red bold]⚠ Near handoff threshold — context reset imminent[/red bold]")
    out.print("")


def render_cost_summary(
    usage: UsageSummary,
    model: str = "",
    pricing: dict[str, float] | None = None,
    target_console: Console | None = None,
) -> None:
    """Render token usage and optional dollar cost from a UsageSummary.

    pricing: if provided, a dict with keys 'input' and 'output' (price per 1M tokens).
    """
    out = target_console or console
    out.print("\n[bold]Session Token Usage[/bold]")
    out.print(f"  Input tokens:  {usage.input_tokens:,}")
    out.print(f"  Output tokens: {usage.output_tokens:,}")
    out.print(f"  Total tokens:  {usage.total_tokens:,}")
    out.print(f"  Turns:         {usage.turns}")
    if pricing and "input" in pricing and "output" in pricing:
        input_cost = usage.input_tokens * pricing["input"] / 1_000_000
        output_cost = usage.output_tokens * pricing["output"] / 1_000_000
        total_cost = input_cost + output_cost
        out.print(f"  Est. cost:     ${total_cost:.4f} ({model})")
    else:
        out.print("  [dim]Tip: configure [pricing] in .kadmon/config.toml for cost estimates[/dim]")
    out.print("")


# --- Rich Rendering Helpers ---


def render_diff(diff_text: str, target_console: Console | None = None) -> None:
    """Render a unified diff with colored lines to the terminal.

    Additions in green, deletions in red, hunk headers in cyan/dim.
    """
    out = target_console or console
    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            out.print(Text(line, style="bold"))
        elif line.startswith("@@"):
            out.print(Text(line, style="cyan dim"))
        elif line.startswith("+"):
            out.print(Text(line, style="green"))
        elif line.startswith("-"):
            out.print(Text(line, style="red"))
        else:
            out.print(Text(line, style="dim"))


_CODE_FENCE_RE = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)


def render_code_block(code: str, language: str = "", target_console: Console | None = None) -> None:
    """Render a fenced code block with syntax highlighting."""
    out = target_console or console
    lexer = language if language else "text"
    syntax = Syntax(code, lexer, theme="monokai", padding=(0, 1))
    out.print(syntax)


def render_message_with_code_blocks(text: str, target_console: Console | None = None) -> None:
    """Post-process a completed message, replacing fenced code blocks with highlighted versions.

    Prose is printed as-is; ```lang ... ``` blocks get syntax highlighting.
    """
    out = target_console or console
    last_end = 0
    for match in _CODE_FENCE_RE.finditer(text):
        # Print prose before this code block
        prose = text[last_end:match.start()]
        if prose.strip():
            out.print(prose, end="")
        lang = match.group(1)
        code = match.group(2)
        render_code_block(code, lang, out)
        last_end = match.end()
    # Trailing prose after last code block
    remaining = text[last_end:]
    if remaining.strip():
        out.print(remaining, end="")


class StreamDisplay:
    """Renders streaming events to the terminal.

    Uses line-aware streaming: prose lines are emitted live, but lines inside
    a code fence are buffered and rendered with syntax highlighting when the
    closing fence arrives. This avoids double-rendering code blocks.
    """

    def __init__(self):
        self._in_text = False
        self._tool_depth = 0
        self._text_buffer = ""
        # Line-aware fence tracking
        self._line_buffer = ""
        self._in_fence = False
        self._fence_lang = ""
        self._fence_lines: list[str] = []

    def handle(self, chunk: StreamChunk):
        """Handle a single stream chunk."""
        if chunk.event == StreamEvent.TEXT_DELTA:
            self._handle_text(chunk.text)
        elif chunk.event == StreamEvent.TOOL_START:
            self._handle_tool_start(chunk.tool_name)
        elif chunk.event == StreamEvent.TOOL_DELTA:
            pass  # Don't show raw JSON streaming
        elif chunk.event == StreamEvent.TOOL_END:
            self._handle_tool_end(chunk.tool_name)
        elif chunk.event == StreamEvent.DONE:
            self._handle_done()

    def show_tool_result(self, tool_name: str, output: str, is_error: bool = False):
        """Show the result of a tool execution."""
        if is_error:
            console.print(f"  [red]✗ {escape(output[:200])}[/red]")
        else:
            # Render diffs with color when tool output looks like a unified diff
            if _looks_like_diff(output):
                render_diff(output)
                return
            # Show truncated output for most tools
            lines = output.strip().split("\n")
            if len(lines) <= 5:
                for line in lines:
                    console.print(f"  [dim]{escape(line)}[/dim]")
            else:
                for line in lines[:3]:
                    console.print(f"  [dim]{escape(line)}[/dim]")
                console.print(f"  [dim]... ({len(lines) - 3} more lines)[/dim]")

    def show_submit(self, patch: str):
        """Show that a patch was submitted."""
        lines = patch.strip().split("\n")
        console.print(f"\n[green bold]✓ Patch generated ({len(lines)} lines)[/green bold]")
        # Show colored diff of the patch
        if _looks_like_diff(patch):
            render_diff(patch)

    def _handle_text(self, text: str):
        if not self._in_text:
            self._in_text = True
            # Reset buffers at the start of a new text turn
            self._text_buffer = ""
            self._line_buffer = ""
        self._text_buffer += text
        self._line_buffer += text
        # Process complete lines
        while "\n" in self._line_buffer:
            line, self._line_buffer = self._line_buffer.split("\n", 1)
            self._process_line(line)

    def _process_line(self, line: str) -> None:
        """Process a single complete line for fence-aware rendering."""
        if not self._in_fence and line.startswith("```"):
            # Opening fence — extract language, start buffering
            self._in_fence = True
            self._fence_lang = line[3:].strip()
            self._fence_lines = []
        elif self._in_fence and line.strip() == "```":
            # Closing fence — render the buffered code block highlighted
            code = "\n".join(self._fence_lines)
            render_code_block(code, self._fence_lang)
            self._in_fence = False
            self._fence_lang = ""
            self._fence_lines = []
        elif self._in_fence:
            # Inside a fence — buffer silently (no raw echo)
            self._fence_lines.append(line)
        else:
            # Prose — stream live
            sys.stdout.write(line + "\n")
            sys.stdout.flush()

    def _flush_fence(self) -> None:
        """Flush any unterminated fence at end of message."""
        if self._in_fence and self._fence_lines:
            code = "\n".join(self._fence_lines)
            render_code_block(code, self._fence_lang)
        self._in_fence = False
        self._fence_lang = ""
        self._fence_lines = []

    def _handle_tool_start(self, tool_name: str):
        if self._in_text:
            # Flush any remaining partial line as prose
            if self._line_buffer:
                if self._in_fence:
                    self._fence_lines.append(self._line_buffer)
                else:
                    sys.stdout.write(self._line_buffer + "\n")
                self._line_buffer = ""
            self._flush_fence()
            sys.stdout.write("\n")
            self._in_text = False
        console.print(f"  [cyan]⚡ {tool_name}[/cyan]", end="")
        self._tool_depth += 1

    def _handle_tool_end(self, tool_name: str):
        self._tool_depth -= 1
        # Tool name was already printed at start; just finish the line
        console.print("")

    def _handle_done(self):
        if self._in_text:
            # Flush any remaining partial line
            if self._line_buffer:
                if self._in_fence:
                    self._fence_lines.append(self._line_buffer)
                else:
                    sys.stdout.write(self._line_buffer)
                self._line_buffer = ""
            self._flush_fence()
            sys.stdout.write("\n")
            self._in_text = False
        self._text_buffer = ""


def _looks_like_diff(text: str) -> bool:
    """Heuristic: does this text look like a unified diff?

    Requires a strong signal — either a `@@ ... @@` hunk header, or BOTH
    a `---` and a `+++` line present. A bare `---` alone (e.g. Markdown
    horizontal rule) does NOT trigger this.
    """
    lines = text.strip().splitlines()[:10]
    has_minus = False
    has_plus = False
    for line in lines:
        if line.startswith("@@") and "@@" in line[2:]:
            return True
        if line.startswith("---"):
            has_minus = True
        if line.startswith("+++"):
            has_plus = True
    return has_minus and has_plus
