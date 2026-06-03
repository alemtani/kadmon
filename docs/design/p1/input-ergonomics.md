# Input Ergonomics: Readline & Multiline

## Problem

The interactive REPL uses bare `input()` — no history navigation, no in-line editing, no
multiline support. Users cannot recall previous prompts with ↑/↓ or paste multi-paragraph
tasks without external workarounds.

## Solution

### Readline Integration

Importing stdlib `readline` before `input()` calls automatically enables:

- Arrow-key history navigation (↑/↓)
- In-line editing (←/→, Home, End, Ctrl-A/E, etc.)
- Ctrl-R reverse search

History persists to `.kadmon/history` (1000 entries) via `atexit` hook. Loaded at REPL
start. No new dependencies — `readline` is stdlib (ships with Python on macOS/Linux;
`pyreadline3` needed on Windows, deferred).

### Multiline Input

Convention: **trailing backslash (`\`) continues input on the next line.**

```
> Write a function that\
... takes a list and\
... returns the sum
```

The prompt changes to `... ` on continuation lines. When the final line has no trailing
backslash, the full assembled text is submitted.

Implementation: `assemble_multiline(lines) -> (text, needs_more)` — a pure function that
determines whether accumulated lines form a complete input. The REPL calls it in a loop.
This is fully unit-testable without stdin mocking.

### Why Trailing Backslash

- Familiar (shell convention, Python line continuation)
- Zero-ambiguity (explicit opt-in to multiline)
- No special start/end markers to remember
- Single-line input (the common case) is unchanged

## Deferred

- **Paste detection** — auto-multiline from rapid multi-line paste (requires terminal raw mode)
- **Fenced paste mode** — triple-backtick markers for verbatim blocks
- **Windows readline** — `pyreadline3` or `prompt_toolkit` for full Windows support
- **Tab completion** — slash commands, file paths (future)

## Files

- `kadmon/cli.py` — `assemble_multiline()`, `_setup_readline()`, `_read_user_input()`
- `tests/test_transparency_ui.py` — multiline assembly unit tests
