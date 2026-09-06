"""``devmemory analyze <version>`` - (re)generate the AI analysis for a version."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.panel import Panel

from devmemory.cli._render import console, warn
from devmemory.services.analysis import analyze_version
from devmemory.services.context import ProjectContext

_RISK_STYLE = {"low": "green", "medium": "yellow", "high": "bold red"}


def analyze_command(
    version: Annotated[str, typer.Argument(help="Version ref: v7, 7, or a commit prefix.")],
    provider: Annotated[
        list[str] | None,
        typer.Option("--provider", "-p", help="Override the provider chain (repeatable)."),
    ] = None,
    no_save: Annotated[
        bool, typer.Option("--no-save", help="Print the analysis without storing it.")
    ] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Emit as JSON.")] = False,
) -> None:
    """Run the analysis provider chain for a version. Interpretation only - it can
    never change the recorded facts."""
    with ProjectContext.load() as ctx:
        analysis = analyze_version(ctx, version, providers=provider or None, persist=not no_save)

    if as_json:
        console.print_json(json.dumps(analysis.model_dump(mode="json")))
        return

    risk = (analysis.risk or "unknown").lower()
    console.print()
    console.print(
        f"[bold cyan]{version.upper()}[/bold cyan]  "
        f"[dim]{analysis.provider}"
        f"{f' · {analysis.model}' if analysis.model else ''}[/dim]  "
        f"risk [{_RISK_STYLE.get(risk, 'white')}]{risk}[/{_RISK_STYLE.get(risk, 'white')}]"
    )
    console.print()
    console.print(Panel(analysis.summary or "(no summary)", title="summary", title_align="left"))
    if analysis.reasoning:
        console.print(f"\n[dim]reasoning:[/dim] {analysis.reasoning}")
    if analysis.recommendation:
        console.print(f"\n[bold]recommendation:[/bold] {analysis.recommendation}")
    for w in analysis.warnings:
        console.print(f"[yellow]![/yellow] {w}")
    if no_save:
        warn("not saved (--no-save)")


__all__ = ["analyze_command"]
