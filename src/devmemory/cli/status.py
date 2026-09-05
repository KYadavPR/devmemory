"""``devmemory status`` - where the project stands right now."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from devmemory.cli._render import check, console, kv_table, warn
from devmemory.domain.models import EntireStatus
from devmemory.services.context import ProjectContext
from devmemory.services.projects import project_status


def status_command(
    as_json: Annotated[bool, typer.Option("--json", help="Emit status as JSON.")] = False,
) -> None:
    """Show the current project, git HEAD, working-tree cleanliness, and Entire state."""
    with ProjectContext.load() as ctx:
        report = project_status(ctx, entire_probe=ctx.entire.probe())

    if as_json:
        console.print_json(json.dumps(report.model_dump(mode="json")))
        return

    head = report.head_sha[:12] if report.head_sha else "(no commits yet)"
    console.print(
        kv_table(
            [
                ("project", f"{report.project.name}  [dim]({report.project.project_id})[/dim]"),
                ("branch", report.branch or "[dim]detached[/dim]"),
                ("HEAD", f"{head}  {report.head_subject or ''}".rstrip()),
                ("working tree", check(report.working_tree_clean)),
                ("versions", str(report.version_count)),
                (
                    "current version",
                    f"V{report.current_version_id}" if report.current_version_id else "-",
                ),
                ("entire", _entire_summary(report.entire)),
            ]
        )
    )
    if not report.working_tree_clean:
        warn("uncommitted changes present")


def _entire_summary(status: EntireStatus) -> str:
    if not status.installed:
        return "not installed"
    if not status.enabled:
        return f"{status.cli_version or 'installed'}, not enabled"
    agents = f" [{', '.join(status.agents)}]" if status.agents else ""
    return f"{status.cli_version or 'enabled'}, enabled{agents}"


__all__ = ["status_command"]
