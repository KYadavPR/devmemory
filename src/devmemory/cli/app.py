"""The ``devmemory`` / ``dm`` entry point.

Phase 0 ships the shell: ``--version`` and a ``version`` command that also reports
the tools DevMemory builds on. Subcommands (``init``, ``checkpoint``, ``serve``,
...) are added in later phases.
"""

from __future__ import annotations

import platform
import shutil
import subprocess

import typer
from rich.console import Console
from rich.table import Table

from devmemory.__about__ import __version__
from devmemory.domain.errors import DevMemoryError

console = Console()
err_console = Console(stderr=True)

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
    _version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_print_version,
        is_eager=True,
        help="Show the DevMemory version and exit.",
    ),
) -> None:
    """DevMemory command-line interface."""


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


def main() -> None:
    """Console-script entry point with top-level error handling."""
    try:
        app()
    except DevMemoryError as exc:
        err_console.print(f"[bold red]error:[/bold red] {exc.message}")
        if exc.hint:
            err_console.print(f"[dim]hint:[/dim] {exc.hint}")
        raise SystemExit(exc.exit_code) from exc
    except KeyboardInterrupt:  # pragma: no cover
        err_console.print("[dim]interrupted[/dim]")
        raise SystemExit(130) from None


if __name__ == "__main__":  # pragma: no cover
    main()
