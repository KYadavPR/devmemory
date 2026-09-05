"""``devmemory diff`` and ``devmemory compare`` - what changed between two versions."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from devmemory.cli._render import console, status_text
from devmemory.services.context import ProjectContext
from devmemory.services.versions import version_diff


def diff_command(
    from_ref: Annotated[str, typer.Argument(metavar="FROM", help="Base version (v6 / 6 / sha).")],
    to_ref: Annotated[str, typer.Argument(metavar="TO", help="Target version.")],
) -> None:
    """Print the exact git diff between two development versions."""
    with ProjectContext.load() as ctx:
        result = version_diff(ctx, from_ref, to_ref)
    console.print(
        f"[dim]{result.from_version_id.upper()} {result.from_commit[:10]} → "
        f"{result.to_version_id.upper()} {result.to_commit[:10]}[/dim]\n"
    )
    console.print(Syntax(result.diff_text or "(no changes)", "diff", theme="ansi_dark"))


def compare_command(
    from_ref: Annotated[str, typer.Argument(metavar="FROM")],
    to_ref: Annotated[str, typer.Argument(metavar="TO")],
    show_diff: Annotated[bool, typer.Option("--diff", help="Also print the git diff.")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Compare two versions: files, lines, metrics, tests, status."""
    with ProjectContext.load() as ctx:
        result = version_diff(ctx, from_ref, to_ref)

    if as_json:
        console.print_json(json.dumps(result.model_dump(mode="json")))
        return

    console.print()
    console.print(
        f"[bold]{result.from_version_id.upper()}[/bold] → [bold]{result.to_version_id.upper()}[/bold]"
        f"   {status_text(result.status_from)} → {status_text(result.status_to)}"
    )
    console.print(
        f"  {result.stat.files_changed} files   "
        f"[green]+{result.stat.additions}[/green] [red]-{result.stat.deletions}[/red]\n"
    )

    if result.files:
        ft = Table(box=None, show_header=False, pad_edge=False)
        ft.add_column(no_wrap=True)
        ft.add_column(overflow="fold")
        ft.add_column(justify="right", no_wrap=True)
        for f in result.files:
            mark = {
                "added": "[green]A[/green]",
                "modified": "[yellow]M[/yellow]",
                "deleted": "[red]D[/red]",
            }.get(f.change_type.value, "[cyan]" + f.change_type.value[0].upper() + "[/cyan]")
            ft.add_row(
                mark,
                f.path,
                "binary"
                if f.binary
                else f"[green]+{f.additions}[/green] [red]-{f.deletions}[/red]",
            )
        console.print(Panel(ft, title="files", title_align="left", border_style="dim"))

    if result.metric_changes:
        mt = Table(box=None, show_header=False, pad_edge=False)
        mt.add_column(no_wrap=True)
        mt.add_column()
        for name, change in result.metric_changes.items():
            before, after, delta = change["before"], change["after"], change["delta"]
            arrow = f"{before} → {after}" if before is not None else str(after)
            tag = ""
            if delta is not None:
                tag = f"  [{'green' if delta >= 0 else 'red'}]({'+' if delta >= 0 else ''}{delta:g})[/]"
            mt.add_row(name, arrow + tag)
        console.print(Panel(mt, title="metrics", title_align="left", border_style="dim"))

    tc = result.test_changes
    if tc.get("passed") is not None:
        console.print(f"  tests: passed {_signed(tc['passed'])}, failed {_signed(tc['failed'])}")

    if show_diff and result.diff_text:
        console.print()
        console.print(Syntax(result.diff_text, "diff", theme="ansi_dark"))


def _signed(n: int | None) -> str:
    if n is None:
        return "?"
    return f"+{n}" if n >= 0 else str(n)


__all__ = ["compare_command", "diff_command"]
