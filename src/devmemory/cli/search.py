"""``devmemory search`` - full-text search across development history."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from devmemory.cli._render import console, status_text
from devmemory.services.context import ProjectContext
from devmemory.services.versions import search_versions


def search_command(
    query: Annotated[
        str, typer.Argument(help="Query: authentication, model.py, Codex, learning rate…")
    ],
    limit: Annotated[int, typer.Option("--limit", "-n")] = 25,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Search versions by intent, agent, feature, files, commit, checkpoint, or analysis."""
    with ProjectContext.load() as ctx:
        results = search_versions(ctx, query, limit=limit)

    if as_json:
        console.print_json(json.dumps([v.model_dump(mode="json") for v in results]))
        return

    if not results:
        console.print(f"[dim]No matches for “{query}”.[/dim]")
        return

    console.print()
    for v in results:
        console.print(
            f"[bold]{v.version_id.upper()}[/bold]  ",
            status_text(v.status),
            f"  [dim]{v.feature_id.split(':')[-1] if v.feature_id else ''}[/dim]",
        )
        console.print(f"  {v.intent or '—'}")
        console.print(
            f"  [dim]{v.agent or '—'} · {v.git_commit[:12]} · "
            f"{', '.join(f.path for f in v.changed_files[:3])}[/dim]\n"
        )


__all__ = ["search_command"]
