"""``devmemory history`` - the version timeline."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.table import Table

from devmemory.cli._render import console, status_text
from devmemory.services.context import ProjectContext
from devmemory.services.versions import list_versions


def history_command(
    limit: Annotated[int, typer.Option("--limit", "-n", help="Most recent N versions.")] = 25,
    as_json: Annotated[bool, typer.Option("--json", help="Emit as JSON.")] = False,
) -> None:
    """List development versions, newest last."""
    with ProjectContext.load() as ctx:
        versions = list_versions(ctx, limit=limit, ascending=False)
    versions.reverse()

    if as_json:
        console.print_json(json.dumps([v.model_dump(mode="json") for v in versions]))
        return

    if not versions:
        console.print("[dim]No versions yet. Run `devmemory checkpoint` after a commit.[/dim]")
        return

    table = Table(box=None, pad_edge=False, header_style="dim")
    table.add_column("", style="bold", no_wrap=True)
    table.add_column("status", no_wrap=True)
    table.add_column("agent", no_wrap=True, max_width=14)
    table.add_column("feature", no_wrap=True, max_width=18)
    table.add_column("Δ", justify="right", no_wrap=True)
    table.add_column("metrics", no_wrap=True, max_width=22)
    table.add_column("intent", overflow="ellipsis", max_width=48)

    for v in versions:
        metrics = " ".join(f"{m.name}={m.after}" for m in v.metrics[:2])
        table.add_row(
            v.version_id.upper(),
            status_text(v.status),
            (v.agent or "-"),
            (v.feature_id.split(":", 1)[-1] if v.feature_id else "-"),
            f"[green]+{v.lines_added}[/green]/[red]-{v.lines_removed}[/red]",
            metrics or "-",
            v.intent or "-",
        )
    console.print(table)


__all__ = ["history_command"]
