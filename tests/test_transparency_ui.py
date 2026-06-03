"""Tests for /context meter, /cost display, and multiline input assembly."""

from dataclasses import dataclass

from rich.console import Console

from kadmon.cli_display import (
    SlashAction,
    handle_slash_command,
    render_context_meter,
    render_cost_summary,
)
from kadmon.cli import assemble_multiline


# --- /context and /cost slash dispatch ---


def test_context_command_dispatches():
    """The /context command returns CONTEXT action."""
    result = handle_slash_command("/context")
    assert result.action == SlashAction.CONTEXT


def test_cost_command_dispatches():
    """The /cost command returns COST action."""
    result = handle_slash_command("/cost")
    assert result.action == SlashAction.COST


def test_help_lists_context_and_cost():
    """The /help output mentions /context and /cost."""
    result = handle_slash_command("/help")
    assert "/context" in result.message
    assert "/cost" in result.message


# --- Context meter rendering ---


@dataclass(frozen=True)
class _FakeStats:
    used_tokens: int
    max_tokens: int
    utilization: float
    message_count: int
    near_handoff: bool


def test_render_context_meter_normal():
    """Context meter shows token counts and utilization."""
    stats = _FakeStats(
        used_tokens=50000, max_tokens=200000, utilization=0.25,
        message_count=12, near_handoff=False,
    )
    console = Console(record=True, force_terminal=True, width=120)
    render_context_meter(stats, target_console=console)
    output = console.export_text()
    assert "50,000" in output
    assert "200,000" in output
    assert "25%" in output
    assert "12" in output
    assert "handoff" not in output.lower() or "near handoff" not in output.lower()


def test_render_context_meter_near_handoff():
    """Context meter shows warning when near_handoff is True."""
    stats = _FakeStats(
        used_tokens=170000, max_tokens=200000, utilization=0.85,
        message_count=40, near_handoff=True,
    )
    console = Console(record=True, force_terminal=True, width=120)
    render_context_meter(stats, target_console=console)
    output = console.export_text()
    assert "170,000" in output
    assert "85%" in output
    assert "handoff" in output.lower()


# --- Cost summary rendering ---


@dataclass(frozen=True)
class _FakeUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    turns: int


def test_render_cost_summary_no_pricing():
    """Cost display shows tokens and a hint when no pricing configured."""
    usage = _FakeUsage(input_tokens=10000, output_tokens=5000, total_tokens=15000, turns=3)
    console = Console(record=True, force_terminal=True, width=120)
    render_cost_summary(usage, model="test-model", pricing=None, target_console=console)
    output = console.export_text()
    assert "10,000" in output
    assert "5,000" in output
    assert "15,000" in output
    assert "3" in output
    assert "config" in output.lower()
    assert "$" not in output


def test_render_cost_summary_with_pricing():
    """Cost display shows dollar estimate when pricing is configured."""
    usage = _FakeUsage(input_tokens=1_000_000, output_tokens=500_000, total_tokens=1_500_000, turns=5)
    pricing = {"input": 3.0, "output": 15.0}
    console = Console(record=True, force_terminal=True, width=120)
    render_cost_summary(usage, model="claude-sonnet", pricing=pricing, target_console=console)
    output = console.export_text()
    # $3/M * 1M input + $15/M * 0.5M output = $3 + $7.5 = $10.5
    assert "$10.5000" in output
    assert "claude-sonnet" in output
    assert "config" not in output.lower()


# --- Multiline assembly ---


def test_assemble_single_line_submits():
    """A single line without trailing backslash submits immediately."""
    text, needs_more = assemble_multiline(["hello world"])
    assert text == "hello world"
    assert needs_more is False


def test_assemble_trailing_backslash_continues():
    """A trailing backslash signals more input needed."""
    _, needs_more = assemble_multiline(["first line\\"])
    assert needs_more is True


def test_assemble_multiline_joins():
    """Multiple lines joined when final line has no backslash."""
    text, needs_more = assemble_multiline(["line one\\", "line two\\", "line three"])
    assert needs_more is False
    assert text == "line one\nline two\nline three"


def test_assemble_empty_needs_more():
    """Empty line list needs more input."""
    _, needs_more = assemble_multiline([])
    assert needs_more is True
