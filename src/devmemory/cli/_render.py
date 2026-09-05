"""Shared Rich rendering helpers for the CLI."""

from __future__ import annotations

from collections.abc import Iterable

from rich.console import Console
from rich.table import Table
from rich.text import Text

from devmemory.domain.enums import VersionStatus

console = Console()
err_console = Console(stderr=True)

_STATUS_STYLE: dict[str, str] = {
    VersionStatus.SUCCESS: "bold green",
    VersionStatus.PARTIAL_SUCCESS: "yellow",
    VersionStatus.ERROR: "bold red",
    VersionStatus.REGRESSION: "bold red",
    VersionStatus.IN_PROGRESS: "cyan",
    VersionStatus.NEEDS_REVIEW: "dim",
}


def status_text(status: str | VersionStatus) -> Text:
    key = str(status)
    return Text(key, style=_STATUS_STYLE.get(key, "white"))


def check(ok: bool) -> Text:
    return Text("yes", style="green") if ok else Text("no", style="red")


def kv_table(rows: Iterable[tuple[str, object]], *, title: str | None = None) -> Table:
    table = Table(show_header=False, box=None, pad_edge=False, title=title, title_justify="left")
    table.add_column(style="bold cyan", no_wrap=True)
    table.add_column(overflow="fold")
    for key, value in rows:
        table.add_row(key, value if isinstance(value, Text) else str(value))
    return table


def hint(text: str) -> None:
    console.print(f"[dim]hint:[/dim] {text}")


def success(text: str) -> None:
    console.print(f"[bold green]✓[/bold green] {text}")


def warn(text: str) -> None:
    console.print(f"[yellow]![/yellow] {text}")


__all__ = [
    "check",
    "console",
    "err_console",
    "hint",
    "kv_table",
    "status_text",
    "success",
    "warn",
]
