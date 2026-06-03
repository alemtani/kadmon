"""Tests for rich rendering helpers (diffs and code blocks)."""

from rich.console import Console

from kadmon.cli_display import (
    StreamDisplay,
    _looks_like_diff,
    render_code_block,
    render_diff,
    render_message_with_code_blocks,
)
from kadmon.providers.base import StreamChunk, StreamEvent


def _capture(fn, *args) -> str:
    """Capture rich output as plain text with markup."""
    console = Console(record=True, force_terminal=True, width=120)
    fn(*args, target_console=console)
    return console.export_text()


def test_render_diff_additions_green():
    """Added lines in a diff contain the + prefix and are rendered."""
    diff = "--- a/file.py\n+++ b/file.py\n@@ -1,3 +1,4 @@\n context\n+added line\n kept\n"
    output = _capture(render_diff, diff)
    assert "+added line" in output


def test_render_diff_deletions():
    """Deleted lines appear in the rendered output."""
    diff = "--- a/file.py\n+++ b/file.py\n@@ -1,3 +1,2 @@\n context\n-removed line\n kept\n"
    output = _capture(render_diff, diff)
    assert "-removed line" in output


def test_render_diff_hunk_headers():
    """Hunk headers (@@ ... @@) appear in output."""
    diff = "--- a/x.py\n+++ b/x.py\n@@ -1,2 +1,2 @@\n-old\n+new\n"
    output = _capture(render_diff, diff)
    assert "@@" in output


def test_render_code_block_python():
    """Python code blocks are rendered without error."""
    code = "def hello():\n    return 'world'\n"
    output = _capture(render_code_block, code, "python")
    assert "hello" in output
    assert "return" in output


def test_render_code_block_unknown_language():
    """Unknown language falls back to plain text rendering."""
    code = "some random text"
    output = _capture(render_code_block, code, "")
    assert "some random text" in output


def test_render_message_with_code_blocks():
    """Fenced code blocks in a message are syntax-highlighted."""
    text = "Here is code:\n```python\ndef foo():\n    pass\n```\nDone."
    output = _capture(render_message_with_code_blocks, text)
    assert "foo" in output
    assert "Done" in output


def test_render_message_no_code_blocks():
    """Messages without code blocks render prose only."""
    text = "Just plain text here."
    output = _capture(render_message_with_code_blocks, text)
    assert "Just plain text" in output


def test_stream_display_code_block_rendered_once(capsys):
    """Code blocks in streamed text must render exactly once (highlighted), not twice."""
    display = StreamDisplay()
    # Simulate streaming a message with a fenced code block
    message = "Before code:\n```python\ndef greet():\n    pass\n```\nAfter code.\n"
    for char in message:
        display.handle(StreamChunk(event=StreamEvent.TEXT_DELTA, text=char))
    display.handle(StreamChunk(event=StreamEvent.DONE))
    captured = capsys.readouterr().out
    # "greet" should appear exactly once (in the highlighted block)
    assert captured.count("greet") == 1
    # The raw fence markers should NOT appear in output (they are consumed)
    assert "```python" not in captured


def test_stream_display_prose_streams_live(capsys):
    """Prose lines outside fences are streamed directly to stdout."""
    display = StreamDisplay()
    display.handle(StreamChunk(event=StreamEvent.TEXT_DELTA, text="Hello world\n"))
    display.handle(StreamChunk(event=StreamEvent.DONE))
    captured = capsys.readouterr().out
    assert "Hello world" in captured


def test_looks_like_diff_false_positive_bare_hr():
    """A bare `---` line (Markdown HR) must NOT be treated as a diff."""
    text = "Some text\n---\nMore text below the rule.\n"
    assert not _looks_like_diff(text)


def test_looks_like_diff_real_diff():
    """A proper unified diff with --- and +++ is detected."""
    text = "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new\n"
    assert _looks_like_diff(text)


def test_looks_like_diff_hunk_header_only():
    """A hunk header alone is enough to detect a diff."""
    text = "@@ -1,5 +1,6 @@\n context\n+new line\n"
    assert _looks_like_diff(text)


def test_stream_display_buffer_reset_between_turns(capsys):
    """The text buffer resets at the start of a new text turn."""
    display = StreamDisplay()
    # First turn
    display.handle(StreamChunk(event=StreamEvent.TEXT_DELTA, text="first\n"))
    display.handle(StreamChunk(event=StreamEvent.DONE))
    # Second turn — buffer should be clean
    display.handle(StreamChunk(event=StreamEvent.TEXT_DELTA, text="second\n"))
    display.handle(StreamChunk(event=StreamEvent.DONE))
    captured = capsys.readouterr().out
    # Both messages appear, no leakage
    assert "first" in captured
    assert "second" in captured
