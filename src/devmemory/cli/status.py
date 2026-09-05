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
    rows: list[tuple[str, object]] = [
        ("project", f"{report.project.name}  [dim]({report.project.project_id})[/dim]"),
        ("branch", report.branch or "[dim]detached[/dim]"),
        ("HEAD", f"{head}  {report.head_subject or ''}".rstrip()),
        ("working tree", check(report.working_tree_clean)),
        ("versions", str(report.version_count)),
    ]
    if report.latest_version_id:
        rows.append(
            (
                "latest",
                f"{report.latest_version_id.upper()}  {report.latest_status}"
                + (f"  [dim]{report.latest_intent}[/dim]" if report.latest_intent else ""),
            )
        )
    if report.latest_metrics:
        rows.append(
            (
                "metrics",
                "  ".join(f"{k}={v}" for k, v in report.latest_metrics.items() if v is not None),
            )
        )
    if report.open_features:
        rows.append(("in progress", ", ".join(report.open_features)))
    if report.last_regression_id:
        rows.append(("last regression", report.last_regression_id.upper()))
    rows.append(("entire", _entire_summary(report.entire)))
    console.print(kv_table(rows))

    if not report.working_tree_clean:
        warn("uncommitted changes present")
    if report.head_sha and not report.head_has_version:
        warn("HEAD is not recorded yet - run `devmemory checkpoint`")


def _entire_summary(status: EntireStatus) -> str:
    if not status.installed:
        return "not installed"
    if not status.enabled:
        return f"{status.cli_version or 'installed'}, not enabled"
    agents = f" [{', '.join(status.agents)}]" if status.agents else ""
    return f"{status.cli_version or 'enabled'}, enabled{agents}"


__all__ = ["status_command"]
