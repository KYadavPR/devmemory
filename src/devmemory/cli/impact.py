"""``devmemory impact <version>`` - the change blast-radius for one version.

Uses the Entire ``graph`` plugin. Enable it with `entire plugin install graph`
and set `graph.enabled = true` to also collect impact during `devmemory
checkpoint`; otherwise this command computes it on demand.
"""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table

from devmemory.cli._render import console, hint, warn
from devmemory.services.context import ProjectContext
from devmemory.services.impact import version_impact
from devmemory.services.versions import get_version

_CHANGE_STYLE = {
    "removed": "bold red",
    "signature_changed": "yellow",
    "renamed": "cyan",
    "added": "green",
    "body_changed": "dim",
}


def impact_command(
    version: Annotated[str, typer.Argument(help="Version ref: v7, 7, or a commit prefix.")],
    as_json: Annotated[bool, typer.Option("--json", help="Emit as JSON.")] = False,
    no_compute: Annotated[
        bool,
        typer.Option("--stored-only", help="Only show a stored result; do not run the analysis."),
    ] = False,
) -> None:
    """Show the entity-level change list and dependent counts for a version."""
    with ProjectContext.load() as ctx:
        v = get_version(ctx, version)
        available = ctx.graph.is_available
        impact = version_impact(ctx, version, compute_if_missing=not no_compute)

    if as_json:
        console.print_json(json.dumps(impact.model_dump(mode="json") if impact else None))
        return

    if impact is None:
        if not available:
            warn("The Entire `graph` plugin is not installed.")
            hint("Install it: entire plugin install graph")
        else:
            warn(f"No impact analysis available for {v.version_id.upper()}.")
        return

    console.print()
    console.print(
        f"[bold cyan]{v.version_id.upper()}[/bold cyan]  "
        f"[dim]{impact.base_commit[:12]} → {impact.head_commit[:12] or 'HEAD'}[/dim]"
    )
    console.print(
        f"{impact.entity_count} changed entities · max dependents {impact.max_dependents}\n"
    )

    if impact.hotspots:
        table = Table(title="Hotspots", title_justify="left", box=None, header_style="dim")
        table.add_column("change")
        table.add_column("entity")
        table.add_column("file", overflow="fold")
        table.add_column("deps", justify="right")
        for e in impact.hotspots:
            style = _CHANGE_STYLE.get(e.change_type, "white")
            table.add_row(
                f"[{style}]{e.change_type}[/{style}]",
                f"{e.kind} {e.name}",
                e.path,
                str(e.dependents_count),
            )
        console.print(table)
        console.print()

    risky = [e for e in impact.entities if e.is_risky]
    if risky:
        lines = "\n".join(
            f"  [bold red]{e.change_type}[/bold red] {e.name} "
            f"[dim]({e.path}, {e.dependents_count} dependents)[/dim]"
            for e in risky
        )
        console.print(
            Panel(lines, title="review before keeping", title_align="left", border_style="red")
        )


__all__ = ["impact_command"]
