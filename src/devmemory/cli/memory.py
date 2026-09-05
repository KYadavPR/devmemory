"""``devmemory memory`` - what failed before, so it isn't tried again."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.panel import Panel

from devmemory.cli._render import console, status_text
from devmemory.services.context import ProjectContext
from devmemory.services.memory import MemoryQuery, previous_attempts


def memory_command(
    files: Annotated[
        list[str] | None,
        typer.Option("--file", "-F", help="A path being changed (repeatable)."),
    ] = None,
    feature: Annotated[str | None, typer.Option("--feature", "-f", help="Feature area.")] = None,
    intent: Annotated[
        str | None, typer.Option("--intent", "-i", help="What you're about to do.")
    ] = None,
    successes: Annotated[
        bool, typer.Option("--include-successes", help="Also show relevant successful attempts.")
    ] = False,
    limit: Annotated[int, typer.Option("--limit", "-n")] = 10,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show previous development attempts relevant to a change - especially failed ones."""
    query = MemoryQuery(
        files=list(files or []),
        feature=feature,
        intent=intent,
        include_successes=successes,
        limit=limit,
    )
    with ProjectContext.load() as ctx:
        attempts = previous_attempts(ctx, query)

    if as_json:
        console.print_json(json.dumps([a.model_dump(mode="json") for a in attempts]))
        return

    if not attempts:
        console.print("[dim]No relevant previous attempts. Nothing to avoid — yet.[/dim]")
        return

    for a in attempts:
        head = f"[bold]{a.version_id.upper()}[/bold]  "
        body = (
            f"[dim]intent[/dim]   {a.intent or '—'}\n"
            f"[dim]change[/dim]   {a.change_summary}\n"
            f"[dim]result[/dim]   {a.result}\n"
            f"[dim]matched[/dim]  {'; '.join(a.matched_on)}"
        )
        if a.recommendation:
            body += f"\n[dim]advice[/dim]   [cyan]{a.recommendation}[/cyan]"
        console.print(
            Panel(
                body,
                title=head + str(status_text(a.status)),
                title_align="left",
                border_style="red" if a.is_adverse else "dim",
            )
        )


__all__ = ["memory_command"]
