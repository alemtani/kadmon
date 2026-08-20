import os
from pathlib import Path

import click

from kadmon import __version__

# --- Multiline Input Assembly (pure, testable) ---


def assemble_multiline(lines: list[str]) -> tuple[str, bool]:
    """Given accumulated raw input lines, determine if more input is needed.

    Convention: a trailing backslash on a line means "continue on next line".
    Returns (assembled_text, needs_more_input).
    """
    if not lines:
        return ("", True)
    last = lines[-1]
    if last.endswith("\\"):
        return ("", True)
    # Join lines, stripping continuation backslashes
    parts = []
    for line in lines:
        if line.endswith("\\"):
            parts.append(line[:-1])
        else:
            parts.append(line)
    return ("\n".join(parts), False)


def _setup_readline(history_path: Path) -> None:
    """Configure readline with persistent history."""
    import readline

    history_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        readline.read_history_file(str(history_path))
    except (FileNotFoundError, OSError):
        pass
    readline.set_history_length(1000)

    import atexit

    def _save_history() -> None:
        try:
            readline.write_history_file(str(history_path))
        except OSError:
            pass

    atexit.register(_save_history)


def _read_user_input(prompt: str = "> ") -> str:
    """Read user input with multiline support (trailing backslash continues)."""
    lines: list[str] = []
    current_prompt = prompt
    while True:
        line = input(current_prompt)
        lines.append(line)
        assembled, needs_more = assemble_multiline(lines)
        if not needs_more:
            return assembled
        current_prompt = "... "


def _make_provider(provider: str, model: str, aws_region: str, repo_path: str = "."):
    """Create the LLM provider named by `provider`, or the configured default.

    Flags win over config, but only when actually passed — click gives us None
    otherwise, which falls through to the configured value.
    """
    from kadmon.config import ConfigError, load_settings
    from kadmon.providers.factory import build_provider

    try:
        settings = load_settings(repo_path)
        config = settings.resolve(provider or "")
        if model:
            config = config.model_copy(update={"model": model})
        if aws_region:
            config = config.model_copy(update={"aws_region": aws_region})
        return build_provider(config)
    except ConfigError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc


@click.group(invoke_without_command=True)
@click.version_option(version=__version__)
@click.option("--model", default=None, help="Override model")
@click.option("--provider", default=None, help="Override provider")
@click.option("--aws-region", default=None, help="AWS region for Bedrock")
@click.pass_context
def main(ctx, model, provider, aws_region):
    """Kadmon - an LLM coding agent."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(chat, model=model, provider=provider, aws_region=aws_region)


@main.command()
@click.option("--model", default=None, help="Override model")
@click.option("--provider", default=None, help="Override provider")
@click.option("--aws-region", default=None, help="AWS region for Bedrock")
def chat(model, provider, aws_region):
    """Interactive chat mode (default when no subcommand given)."""
    from kadmon.agent import AgentLoop
    from kadmon.cli_display import (
        SlashAction,
        StreamDisplay,
        handle_slash_command,
        render_context_meter,
        render_cost_summary,
    )
    from kadmon.human import CLIChannel
    from kadmon.memory.librarian import Librarian
    from kadmon.memory.session_tracker import SessionTracker
    from kadmon.tools import build_index, create_default_registry

    repo_path = os.path.abspath(".")
    llm = _make_provider(provider, model, aws_region, repo_path)
    _provider = getattr(llm, "name", provider or "default")
    _model = getattr(llm, "model", model or "")
    db = build_index(repo_path)
    tools = create_default_registry(repo_path, db=db, provider=llm)
    librarian = Librarian(repo_path)
    session_tracker = SessionTracker(repo_path)
    channel = CLIChannel()
    display = StreamDisplay()

    # Set up readline for history and in-line editing
    history_path = Path(repo_path) / ".kadmon" / "history"
    _setup_readline(history_path)

    click.echo("Kadmon — type your task, then press Enter. Ctrl+C to exit.\n")
    click.echo("  Multiline: end a line with \\ to continue on the next line.\n")

    from kadmon.conversation import ConversationHistory
    conv_history = ConversationHistory(repo_path)

    # Load pricing config if available
    pricing = _load_pricing(repo_path)

    task = ""
    agent = AgentLoop(
        provider=llm,
        tools=tools,
        librarian=librarian,
        session_tracker=session_tracker,
        channel=channel,
        repo_root=repo_path,
        display=display,
    )
    first_prompt = True
    try:
        while True:
            task = _read_user_input("> ").strip()
            if not task:
                continue
            # Handle slash commands
            if task.startswith("/"):
                result = handle_slash_command(task)
                if result.action == SlashAction.EXIT:
                    click.echo("Bye.")
                    break
                elif result.action == SlashAction.CLEAR:
                    agent = AgentLoop(
                        provider=llm,
                        tools=tools,
                        librarian=librarian,
                        session_tracker=session_tracker,
                        channel=channel,
                        repo_root=repo_path,
                        display=display,
                    )
                    first_prompt = True
                    click.echo("Context cleared.")
                elif result.action == SlashAction.STATUS:
                    _print_status(repo_path)
                elif result.action == SlashAction.CHECKPOINTS:
                    _print_checkpoints(repo_path)
                elif result.action == SlashAction.PROVIDERS:
                    _print_providers(repo_path, _provider)
                elif result.action == SlashAction.MODEL:
                    click.echo(f"Provider: {_provider}  Model: {_model}")
                elif result.action == SlashAction.CONTEXT:
                    render_context_meter(agent.context.stats())
                elif result.action == SlashAction.COST:
                    render_cost_summary(
                        agent.usage_summary(),
                        model=_model,
                        pricing=pricing,
                    )
                elif result.action in (SlashAction.HELP, SlashAction.UNKNOWN):
                    click.echo(result.message)
                continue
            conv_history.snapshot(task, [], None)
            if first_prompt:
                result = agent.run(task)
                first_prompt = False
            else:
                result = agent.continue_with(task)
            if result:
                click.echo("")
            else:
                click.echo("\nDone.\n")
    except KeyboardInterrupt:
        click.echo("\nSaving session...")
        library_path = Path(repo_path) / ".kadmon" / "library"
        sessions_dir = library_path / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        current_path = sessions_dir / "current.md"
        if task:
            current_path.write_text(f"# Interrupted Session\n\nLast task: {task}\n")
        click.echo("Session saved. Use 'kadmon continue' to resume.")
    except EOFError:
        click.echo("\nBye.")
    finally:
        db.close()


@main.command("continue")
@click.option("--model", default=None, help="Override model")
@click.option("--provider", default=None, help="Override provider")
@click.option("--aws-region", default=None, help="AWS region for Bedrock")
def continue_session(model, provider, aws_region):
    """Resume the previous task from sessions/current.md."""
    from kadmon.agent import AgentLoop
    from kadmon.cli_display import StreamDisplay
    from kadmon.human import CLIChannel
    from kadmon.memory.librarian import Librarian
    from kadmon.memory.session_tracker import SessionTracker
    from kadmon.tools import build_index, create_default_registry

    repo_path = os.path.abspath(".")

    library_path = Path(repo_path) / ".kadmon" / "library"
    current_path = library_path / "sessions" / "current.md"

    if not current_path.exists() or not current_path.read_text().strip():
        click.echo("No saved session found. Nothing to continue.")
        raise SystemExit(1)

    task = current_path.read_text()
    click.echo("Resuming session...\n")

    llm = _make_provider(provider, model, aws_region, repo_path)
    db = build_index(repo_path)
    tools = create_default_registry(repo_path, db=db, provider=llm)
    librarian = Librarian(repo_path)
    session_tracker = SessionTracker(repo_path)
    channel = CLIChannel()
    display = StreamDisplay()

    agent = AgentLoop(
        provider=llm,
        tools=tools,
        librarian=librarian,
        session_tracker=session_tracker,
        channel=channel,
        repo_root=repo_path,
        display=display,
    )
    result = agent.run(task)
    db.close()
    if result:
        click.echo(result)
    else:
        click.echo("\nDone.\n")


@main.command()
@click.option("--task", required=True, type=str, help="Task description")
@click.option("--repo", default=".", type=click.Path(exists=True), help="Repository path")
@click.option("--model", default=None, type=str, help="Model to use")
@click.option("--provider", default=None, help="Configured provider name")
@click.option("--aws-region", default=None, help="AWS region for Bedrock")
@click.option(
    "--mode",
    type=click.Choice(["yolo", "cautious", "paranoid"]),
    default="cautious",
    help="Agent mode",
)
def run(task: str, repo: str, model: str, provider: str, aws_region: str, mode: str):
    """Run kadmon on a task."""
    from kadmon.agent import AgentLoop
    from kadmon.human import CLIChannel
    from kadmon.memory.librarian import Librarian
    from kadmon.memory.session_tracker import SessionTracker
    from kadmon.tools import build_index, create_default_registry

    repo_path = os.path.abspath(repo)
    llm = _make_provider(provider, model, aws_region, repo_path)
    db = build_index(repo_path)
    tools = create_default_registry(repo_path, db=db, provider=llm)
    librarian = Librarian(repo_path)
    session_tracker = SessionTracker(repo_path)
    channel = CLIChannel() if mode != "yolo" else None
    agent = AgentLoop(
        provider=llm,
        tools=tools,
        librarian=librarian,
        session_tracker=session_tracker,
        mode=mode,
        channel=channel,
        repo_root=repo_path,
    )
    result = agent.run(task)
    db.close()
    if result:
        click.echo(result)
    else:
        click.echo("Agent did not produce a result.", err=True)


@main.command("eval")
@click.option("--dataset", type=click.Path(exists=True), help="Path to SWE-bench instances JSON")
@click.option("--limit", type=int, default=None, help="Max instances to run")
@click.option("--output", default="eval_results", help="Output directory")
@click.option("--model", default=None, help="Override model")
@click.option("--provider", default=None, help="Configured provider name")
def eval_cmd(dataset, limit, output, model, provider):
    """Run kadmon against SWE-bench instances."""
    import json

    from kadmon.eval import SWEBenchRunner

    if not dataset:
        click.echo("Error: --dataset required (path to instances JSON)", err=True)
        raise SystemExit(1)

    with open(dataset) as f:
        instances = json.load(f)

    if limit:
        instances = instances[:limit]

    label = model or provider or "configured provider"
    click.echo(f"Running {len(instances)} instances with {label}...")
    runner = SWEBenchRunner(model=model or "", provider=provider or "")
    summary = runner.run_dataset(instances, output_dir=output)
    click.echo(
        f"\nResults: {summary.resolved}/{summary.total} resolved ({summary.resolve_rate:.1%})"
    )
    click.echo(f"Errors: {summary.errored}")
    click.echo(f"Output: {output}/")


@main.command("bench")
@click.option(
    "--languages",
    default=None,
    help="Comma-separated languages (python,javascript,go,rust,java,cpp)",
)
@click.option("--limit", type=int, default=None, help="Max exercises to run")
@click.option("--output", default="eval_results/polyglot", help="Output directory")
@click.option("--model", default=None, help="Override model")
@click.option("--provider", default=None, help="Configured provider name")
@click.option("--aws-region", default=None, help="AWS region for Bedrock")
@click.option("--setup/--no-setup", default=True, help="Clone exercism repos if needed")
@click.option("--workers", "-j", type=int, default=4, help="Parallel workers (default: 4)")
def bench(languages, limit, output, model, provider, aws_region, setup, workers):
    """Run Aider Polyglot benchmark."""
    from kadmon.eval.polyglot import PolyglotRunner

    langs = languages.split(",") if languages else None
    runner = PolyglotRunner(
        model=model,
        provider=provider,
        aws_region=aws_region,
        languages=langs,
        workers=workers,
    )
    if setup:
        click.echo("Setting up exercism repos...")
        runner.setup()

    click.echo(f"Running polyglot benchmark ({limit or 'all'} exercises, {workers} workers)...")
    summary = runner.run(limit=limit, output_dir=output)
    click.echo("\nResults:")
    click.echo(
        f"  Pass rate (try 1): {summary.passed_try1}/{summary.total} ({summary.pass_rate_1:.1%})"
    )
    click.echo(
        f"  Pass rate (try 2): {summary.passed_try2}/{summary.total} ({summary.pass_rate_2:.1%})"
    )
    click.echo(f"  Errors: {summary.errors}")
    click.echo(f"  Output: {output}/")


@main.command()
@click.option("--repo", default=".", type=click.Path(exists=True), help="Repository path")
@click.option("--global", "show_global", is_flag=True, help="Show sessions across all projects")
def status(repo: str, show_global: bool):
    """Show current session state and library summary."""
    _print_status(repo, show_global)


def _print_status(repo: str = ".", show_global: bool = False) -> None:
    """Core logic for showing session state and library summary.

    Called by both the Click command and the /status slash handler.
    """
    if show_global:
        from kadmon.memory.central_index import CentralIndex
        index = CentralIndex()
        sessions = index.list_recent(days=14)
        if not sessions:
            click.echo("No recent sessions found across projects.")
            return
        click.echo("\n=== Recent Sessions (last 14 days) ===\n")
        for s in sessions:
            status_icon = {"in_progress": "⏳", "completed": "✓", "handed_off": "↗"}.get(s.status, s.status)
            click.echo(f"  {status_icon} [{s.session_key}] {s.task}")
            click.echo(f"    Repo: {s.repo}")
            click.echo(f"    Updated: {s.last_updated}")
            click.echo("")
        return

    from kadmon.memory.session_tracker import SessionTracker

    repo_path = os.path.abspath(repo)
    kadmon_dir = Path(repo_path) / ".kadmon"

    if not kadmon_dir.exists():
        click.echo("No .kadmon directory found. Run 'kadmon init' or start a task first.")
        return

    # --- Session status ---
    tracker = SessionTracker(repo_path)
    session = tracker.load()

    click.echo("\n=== Kadmon Status ===\n")

    if session is None:
        click.echo("Session:   no active session")
    else:
        status_icon = {"in_progress": "⏳", "completed": "✓", "handed_off": "↗"}.get(
            session.status, session.status
        )
        click.echo(f"Session:   {session.session_id}  [{status_icon} {session.status}]")
        click.echo(f"Started:   {session.started}")
        click.echo(f"Task:      {session.task}")

        delegations = session.delegations
        if delegations:
            click.echo(f"\nDelegations ({len(delegations)}):")
            for d in delegations:
                icon = {"completed": "✓", "failed": "✗", "in_progress": "⏳"}.get(d.status, d.status)
                line = f"  {icon} [{d.id}] {d.task}"
                if d.summary:
                    line += f"\n       → {d.summary}"
                click.echo(line)
        else:
            click.echo("\nDelegations: none")

    # --- Library summary ---
    library_path = kadmon_dir / "library"
    click.echo("")
    if not library_path.exists():
        click.echo("Library:   empty (no .kadmon/library/ yet)")
    else:
        index_path = library_path / "index.md"
        if index_path.exists() and index_path.stat().st_size > 0:
            click.echo("Library:")
            for line in index_path.read_text().splitlines():
                if line.strip() and not line.startswith("#"):
                    click.echo(f"  {line.strip()}")
        else:
            files = list(library_path.glob("*.md"))
            if files:
                click.echo(f"Library:   {len(files)} file(s) in .kadmon/library/")
            else:
                click.echo("Library:   empty")

        # Session history count
        sessions_dir = kadmon_dir / "sessions"
        if sessions_dir.exists():
            count = len(list(sessions_dir.glob("*.json")))
            if count:
                click.echo(f"\nHistory:   {count} archived session(s) in .kadmon/sessions/")

    # --- Session history (always check, independent of library) ---
    sessions_dir = kadmon_dir / "sessions"
    if sessions_dir.exists():
        count = len(list(sessions_dir.glob("*.json")))
        if count:
            click.echo(f"\nHistory:   {count} archived session(s)")

    click.echo("")


@main.command()
@click.option("--with-files", is_flag=True, help="Also rollback file changes")
def rewind(with_files: bool):
    """Rewind conversation to a previous prompt."""
    from kadmon.conversation import ConversationHistory

    repo_path = os.path.abspath(".")
    history = ConversationHistory(repo_path)
    turns = history.list_turns()
    if not turns:
        click.echo("No conversation history to rewind to.")
        return
    click.echo("\nRecent prompts:")
    for t in turns:
        click.echo(f"  [{t['turn_id']}] \"{t['prompt']}\"")
    click.echo("")
    choice = click.prompt("Rewind to before which prompt?", type=int)
    turn = history.rewind(choice)
    if not turn:
        click.echo(f"Turn {choice} not found.")
        return
    if with_files:
        from kadmon.checkpoints import CheckpointManager

        mgr = CheckpointManager(repo_path)
        for cp in mgr.list():
            if cp["timestamp"] > turn.timestamp:
                mgr.rollback(cp["id"])
    click.echo(f"\u2713 Conversation restored to before prompt {choice}. {'Files also restored.' if with_files else 'Files unchanged.'}")
    click.echo("Start kadmon to continue from this point.")


@main.command()
@click.argument("checkpoint_id", required=False)
def rollback(checkpoint_id):
    """Rollback file changes to a checkpoint."""
    from kadmon.checkpoints import CheckpointManager

    repo_path = os.path.abspath(".")
    mgr = CheckpointManager(repo_path)
    restored = mgr.rollback(checkpoint_id)
    if not restored:
        click.echo("No checkpoint to rollback to.")
        return
    click.echo(f"\u2713 Restored {len(restored)} file(s):")
    for f in restored:
        click.echo(f"  {f}")


@main.command()
def checkpoints():
    """List available file checkpoints."""
    _print_checkpoints()


def _print_providers(repo_path: str, current: str = "") -> None:
    """List every configured provider, marking the one in use."""
    from kadmon.config import ConfigError, load_settings

    try:
        settings = load_settings(repo_path)
    except ConfigError as exc:
        click.echo(f"  {exc}")
        return

    if not settings.providers:
        click.echo("  No providers configured. Run 'kadmon init'.")
        return

    click.echo("\nConfigured providers:")
    for name, config in sorted(settings.providers.items()):
        mark = "*" if name == current else " "
        where = f" via {config.base_url}" if config.base_url else ""
        click.echo(f"  {mark} {name:12} {config.kind:10} {config.model}{where}")
    click.echo(f"\n  default: {settings.default or '(only one configured)'}\n")


def _print_checkpoints(repo: str = ".") -> None:
    """Core logic for listing checkpoints.

    Called by both the Click command and the /checkpoints slash handler.
    """
    from kadmon.checkpoints import CheckpointManager

    repo_path = os.path.abspath(repo)
    mgr = CheckpointManager(repo_path)
    cps = mgr.list()
    if not cps:
        click.echo("No checkpoints available.")
        return
    click.echo("\nCheckpoints:")
    for cp in cps:
        files = ", ".join(cp["files"])
        click.echo(f"  [{cp['id']}] {cp['tool']} \u2014 {files}")
    click.echo("")


def _load_pricing(repo_path: str) -> dict[str, float] | None:
    """Load model pricing from the merged config [pricing] section, if present.

    Expected format in config.toml:
        [pricing]
        input = 3.0    # dollars per 1M input tokens
        output = 15.0  # dollars per 1M output tokens

    Returns None if not configured.
    """
    from kadmon.config import ConfigError, load_settings

    try:
        pricing = load_settings(repo_path).pricing
    except ConfigError:
        return None
    if "input" in pricing and "output" in pricing:
        return pricing
    return None


@main.command()
@click.option("--local", is_flag=True, help="Write to this project instead of your home config")
def init(local):
    """Interactive setup — detect providers, pick the ones you want, test them."""
    from kadmon.config import (
        CREDENTIALS_PATH,
        GLOBAL_CONFIG_PATH,
        KIND_DEFAULTS,
        PROJECT_CONFIG_RELPATH,
        write_config,
        write_credential,
    )
    from kadmon.providers.discovery import discover

    click.echo("\n\u2728 Kadmon Setup\n")

    candidates = discover()
    click.echo("Found on this machine:")
    for i, c in enumerate(candidates, 1):
        mark = "\u2713" if c.available else " "
        click.echo(f"  [{mark}] {i}. {c.label:16} {c.detail}")

    click.echo("\nSelect providers to enable (comma-separated numbers).")
    click.echo("You can pick several — kadmon keeps them all configured.")
    ready = [str(i) for i, c in enumerate(candidates, 1) if c.available]
    picked = click.prompt("Providers", default=",".join(ready) or "1")

    chosen: list = []
    for token in picked.split(","):
        token = token.strip()
        if not token.isdigit() or not 1 <= int(token) <= len(candidates):
            click.echo(f"Ignoring '{token}' — not one of the numbers above.")
            continue
        chosen.append(candidates[int(token) - 1])

    if not chosen:
        click.echo("Nothing selected. Run 'kadmon init' again to pick a provider.", err=True)
        raise SystemExit(1)

    configs = []
    for c in chosen:
        click.echo(f"\n{c.label}")
        model = click.prompt("  Model", default=c.model or KIND_DEFAULTS[c.kind]["model"])
        config = c.to_config().model_copy(update={"model": model})

        if not c.available and c.auth.startswith("env:"):
            key = click.prompt("  API key", hide_input=True, default="", show_default=False)
            if key:
                write_credential(c.name, key)
                config = config.model_copy(update={"auth": f"credentials:{c.name}"})
                click.echo(f"  Key stored in {CREDENTIALS_PATH}")
        configs.append(config)

    click.echo("\nTesting connections...")
    working = []
    for config in configs:
        ok, detail = _test_provider(config)
        mark = "\u2713" if ok else "\u2717"
        click.echo(f"  {mark} {config.name}: {detail}")
        if ok:
            working.append(config)

    if not working:
        if not click.confirm("\nNothing connected. Save anyway?"):
            raise SystemExit(1)
        working = configs

    names = [c.name for c in working]
    default = names[0] if len(names) == 1 else click.prompt(
        "\nDefault provider", type=click.Choice(names), default=names[0]
    )

    path = Path(".") / PROJECT_CONFIG_RELPATH if local else GLOBAL_CONFIG_PATH
    write_config(working, default, path)

    click.echo(f"\n\u2713 Saved {len(working)} provider(s) to {path}")
    click.echo(f"  Default: {default}")
    if len(working) > 1:
        others = ", ".join(n for n in names if n != default)
        click.echo(f"  Switch anytime: kadmon --provider {others.split(',')[0].strip()}")
    click.echo('\nTry: kadmon run --task "Describe what this project does"')


def _test_provider(config) -> tuple[bool, str]:
    """Make a minimal call to verify a provider actually works."""
    from kadmon.providers.base import Message
    from kadmon.providers.factory import build_provider

    try:
        provider = build_provider(config, max_tokens=16)
        provider.complete(
            messages=[Message(role="user", content="Say ok")], system="Respond with just 'ok'"
        )
        return True, "connected"
    except Exception as exc:  # noqa: BLE001 - report any failure to the user verbatim
        return False, str(exc).split("\n")[0][:80]


