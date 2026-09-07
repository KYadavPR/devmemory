"""The ``devmemory`` / ``dm`` entry point.

Thin Typer layer: each command lives in its own module and is registered here.
Top-level error handling turns :class:`DevMemoryError` into a clean message +
hint + exit code.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from typing import Annotated

import typer
from rich.table import Table

from devmemory.__about__ import __version__
from devmemory.cli._errors import handle_errors
from devmemory.cli._render import console, err_console
from devmemory.cli.analytics import analytics_command, databricks_app
from devmemory.cli.analyze import analyze_command
from devmemory.cli.backfill import backfill_command
from devmemory.cli.checkpoint import checkpoint_command
from devmemory.cli.compare import compare_command, diff_command
from devmemory.cli.doctor import doctor_command
from devmemory.cli.history import history_command
from devmemory.cli.impact import impact_command
from devmemory.cli.init import init_command
from devmemory.cli.mcp import mcp_command
from devmemory.cli.memory import memory_command
from devmemory.cli.model import model_app
from devmemory.cli.restore import restore_command
from devmemory.cli.search import search_command
from devmemory.cli.serve import serve_command
from devmemory.cli.show import show_command
from devmemory.cli.status import status_command
from devmemory.cli.task import state_command, task_app
from devmemory.domain.errors import DevMemoryError
from devmemory.logging import configure_logging

app = typer.Typer(
    name="devmemory",
    help=(
        "DevMemory - development-memory and version-intelligence for AI-assisted "
        "software development.\n\n"
        "Git remembers what changed. Entire remembers the AI-assisted context. "
        "DevMemory connects them with results, so you and the next agent can see "
        "the whole story."
    ),
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _print_version(value: bool) -> None:
    if value:
        console.print(f"devmemory {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    _version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            callback=_print_version,
            is_eager=True,
            help="Show the DevMemory version and exit.",
        ),
    ] = False,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show info-level diagnostic logs.")
    ] = False,
) -> None:
    """DevMemory command-line interface."""
    _load_dotenv()
    level = os.environ.get("DEVMEMORY_LOG_LEVEL") or ("INFO" if verbose else "WARNING")
    configure_logging(level=level, json_logs=False)


def _load_dotenv() -> None:
    """Load a ``.env`` (searched from the cwd upward) so credentials can live in a
    file. Real environment variables always win - ``.env`` never overrides them."""
    from dotenv import find_dotenv, load_dotenv

    found = find_dotenv(usecwd=True)
    if found:
        load_dotenv(found, override=False)


def _tool_version(executable: str, args: list[str]) -> str:
    path = shutil.which(executable)
    if path is None:
        return "[dim]not found[/dim]"
    try:
        result = subprocess.run(  # noqa: S603 - fixed executable, no shell
            [path, *args],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "[yellow]error[/yellow]"
    output = (result.stdout or result.stderr).strip().splitlines()
    return output[0].strip() if output else "[green]present[/green]"


@app.command()
def version() -> None:
    """Show the DevMemory version and the toolchain it detects."""
    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_column(style="bold cyan")
    table.add_column()
    table.add_row("DevMemory", __version__)
    table.add_row("Python", platform.python_version())
    table.add_row("Platform", f"{platform.system()} {platform.release()} ({platform.machine()})")
    table.add_row("git", _tool_version("git", ["--version"]))
    table.add_row("entire", _tool_version("entire", ["version"]))
    console.print(table)


app.command(name="init")(handle_errors(init_command))
app.command(name="doctor")(handle_errors(doctor_command))
app.command(name="status")(handle_errors(status_command))
app.command(name="checkpoint")(handle_errors(checkpoint_command))
app.command(name="backfill")(handle_errors(backfill_command))
app.command(name="history")(handle_errors(history_command))
app.command(name="show")(handle_errors(show_command))
app.command(name="diff")(handle_errors(diff_command))
app.command(name="compare")(handle_errors(compare_command))
app.command(name="impact")(handle_errors(impact_command))
app.command(name="analyze")(handle_errors(analyze_command))
app.add_typer(model_app, name="model")
app.command(name="search")(handle_errors(search_command))
app.command(name="memory")(handle_errors(memory_command))
app.command(name="restore")(handle_errors(restore_command))
app.command(name="analytics")(handle_errors(analytics_command))
app.add_typer(databricks_app, name="databricks")
app.command(name="serve")(handle_errors(serve_command))
app.command(name="mcp")(handle_errors(mcp_command))
app.add_typer(task_app, name="task")
app.command(name="state")(handle_errors(state_command))


def main() -> None:
    """Console-script entry point with top-level error handling."""
    try:
        app()
    except DevMemoryError as exc:
        from rich.markup import escape

        err_console.print(f"[bold red]error:[/bold red] {escape(exc.message)}")
        if exc.hint:
            err_console.print(f"[dim]hint:[/dim] {escape(exc.hint)}")
        raise SystemExit(exc.exit_code) from exc
    except KeyboardInterrupt:  # pragma: no cover
        err_console.print("[dim]interrupted[/dim]")
        raise SystemExit(130) from None


if __name__ == "__main__":  # pragma: no cover
    main()
