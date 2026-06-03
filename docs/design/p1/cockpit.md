# Cockpit Ergonomics: Slash Commands & Rich Rendering

## Problem

The interactive chat REPL uses a bare `input()` loop with no in-session commands.
Tool output (diffs, code) renders as plain monochrome text — no color differentiation
for additions/deletions, no syntax highlighting for code blocks.

## Slash Commands

### Design

A pure dispatcher function `handle_slash_command(cmd: str) -> SlashResult` maps input
to a `SlashAction` enum. The REPL acts on the result. This separation keeps dispatch
unit-testable without stdin mocking.

### Implemented Commands

| Command       | Action                                      |
|---------------|---------------------------------------------|
| `/help`       | Print available commands                    |
| `/clear`      | Reset conversation (new AgentLoop instance) |
| `/status`     | Reuse existing `status` command logic       |
| `/checkpoints`| Reuse existing `checkpoints` command logic  |
| `/model`      | Print current provider and model name       |
| `/exit`,`/quit`| Exit the REPL cleanly                      |

Non-slash input passes to the agent unchanged.

### Deferred

- `/cost` — requires token-usage accumulation instrumentation (not yet wired)
- Line editing / history (readline/prompt_toolkit) — separate roadmap item
- `/undo`, `/rollback` — needs tighter agent-state integration

## Rendering Helpers

### Colored Diffs — `render_diff()`

Per-line coloring of unified diffs: additions green, deletions red, hunk headers
cyan/dim, file headers bold, context lines dim. Integrated into `show_tool_result`
and `show_submit` — any output that looks like a unified diff is auto-colored.

### Syntax-Highlighted Code — `render_code_block()`

Uses `rich.syntax.Syntax` with language hint from fence markers. Fallback: `text` lexer.

### Integration Choice

Prose streams line-by-line via `sys.stdout.write` (low latency). `StreamDisplay._handle_text`
is line-aware: it tracks whether the current position is inside a code fence. Prose lines
outside fences are emitted live; lines inside a fence are buffered silently and rendered as a
syntax-highlighted block (via `render_code_block`) when the closing fence arrives. Any
unterminated fence is flushed at `_handle_done`. This approach renders code blocks exactly once,
with highlighting, while preserving streaming latency for prose.

## Testing

- `tests/test_slash_commands.py` — 10 tests covering each command, unknown handling,
  case insensitivity, whitespace stripping
- `tests/test_rendering.py` — 7 tests using `Console(record=True)` to capture and assert
  rendered output for diffs and code blocks

## Files Changed

- `kadmon/cli_display.py` — slash dispatch + rendering helpers + integration
- `kadmon/cli.py` — slash command handling in chat REPL loop
- `tests/test_slash_commands.py` — new
- `tests/test_rendering.py` — new
