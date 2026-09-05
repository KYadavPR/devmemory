"""``devmemory init`` - set DevMemory up in the current repository."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from devmemory.adapters.entire import EntireAdapter
from devmemory.cli._render import check, console, hint, kv_table, success, warn
from devmemory.domain.models import EntireStatus
from devmemory.services.projects import init_project


def init_command(
    name: Annotated[str | None, typer.Option("--name", help="Human-readable project name.")] = None,
    project_id: Annotated[
        str | None,
        typer.Option("--project-id", help="Stable slug id (default: derived from name)."),
    ] = None,
    force: Annotated[
        bool, typer.Option("--force", help="Re-create configuration even if already initialized.")
    ] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Emit the init report as JSON.")] = False,
) -> None:
    """Initialize DevMemory tracking in the current git repository.

    Creates a `.devmemory/` directory (config, SQLite database), registers the
    project, and reports what git and Entire look like here.
    """
    repo_path = Path.cwd()
    entire = EntireAdapter(repo_path).probe()
    report = init_project(
        repo_path,
        name=name,
        project_id=project_id,
        force=force,
        entire_probe=entire,
    )

    if as_json:
        console.print_json(json.dumps(report.model_dump(mode="json")))
        return

    success(f"DevMemory initialized for [bold]{report.project.name}[/bold]")
    console.print(
        kv_table(
            [
                ("project id", report.project.project_id),
                ("repository", report.project.repo_path),
                ("config", report.config_path),
                ("database", report.db_path),
                ("git", report.git_version or "detected"),
                ("entire", _entire_line(report.entire)),
                ("python", report.environment.python_version),
            ]
        )
    )

    if report.gitignore_updated:
        console.print("[dim]added DevMemory entries to .gitignore[/dim]")
    if not report.entire.installed:
        warn("Entire CLI not found - versions will be recorded without checkpoint context.")
        hint("Install Entire from https://entire.io, then run `entire enable`.")
    elif not report.entire.enabled:
        warn("Entire is installed but not enabled in this repository.")
        hint("Run `entire enable` so AI sessions are captured as checkpoints.")

    console.print()
    console.print(
        "Next: make an AI-assisted change, commit it, then run [bold]devmemory checkpoint[/bold]."
    )


def _entire_line(status: EntireStatus) -> object:
    if not status.installed:
        return check(False)
    label = f"{status.cli_version or 'installed'}"
    if status.enabled:
        label += " (enabled"
        if status.agents:
            label += f", {', '.join(status.agents)}"
        label += ")"
    else:
        label += " (not enabled)"
    return label


__all__ = ["init_command"]
