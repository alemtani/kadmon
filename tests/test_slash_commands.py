"""Tests for slash command dispatch."""

from kadmon.cli_display import SlashAction, SlashResult, handle_slash_command


def test_help_command():
    """The /help command returns HELP action with help text."""
    result = handle_slash_command("/help")
    assert result.action == SlashAction.HELP
    assert "/help" in result.message
    assert "/exit" in result.message


def test_clear_command():
    """The /clear command returns CLEAR action."""
    result = handle_slash_command("/clear")
    assert result.action == SlashAction.CLEAR


def test_status_command():
    """The /status command returns STATUS action."""
    result = handle_slash_command("/status")
    assert result.action == SlashAction.STATUS


def test_checkpoints_command():
    """The /checkpoints command returns CHECKPOINTS action."""
    result = handle_slash_command("/checkpoints")
    assert result.action == SlashAction.CHECKPOINTS


def test_model_command():
    """The /model command returns MODEL action."""
    result = handle_slash_command("/model")
    assert result.action == SlashAction.MODEL


def test_exit_command():
    """The /exit command returns EXIT action."""
    result = handle_slash_command("/exit")
    assert result.action == SlashAction.EXIT


def test_quit_command():
    """The /quit command is an alias for /exit."""
    result = handle_slash_command("/quit")
    assert result.action == SlashAction.EXIT


def test_unknown_command():
    """Unknown slash commands return UNKNOWN with an error message."""
    result = handle_slash_command("/foobar")
    assert result.action == SlashAction.UNKNOWN
    assert "Unknown command" in result.message
    assert "/foobar" in result.message


def test_case_insensitive():
    """Commands are case-insensitive."""
    result = handle_slash_command("/HELP")
    assert result.action == SlashAction.HELP


def test_whitespace_stripped():
    """Leading/trailing whitespace is stripped."""
    result = handle_slash_command("  /exit  ")
    assert result.action == SlashAction.EXIT


def test_handle_slash_command_return_type():
    """handle_slash_command returns a SlashResult with proper type."""
    result = handle_slash_command("/help")
    assert isinstance(result, SlashResult)


def test_print_status_callable(tmp_path):
    """_print_status can be called directly without CliRunner."""
    from kadmon.cli import _print_status

    # Should run without error on a dir without .kadmon
    _print_status(str(tmp_path))


def test_print_checkpoints_callable(tmp_path):
    """_print_checkpoints can be called directly without CliRunner."""
    from kadmon.cli import _print_checkpoints

    # Should run without error on a dir without checkpoints
    _print_checkpoints(str(tmp_path))
