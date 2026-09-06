"""``devmemory analytics`` and ``devmemory databricks``."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table

from devmemory.cli._render import console, hint, success, warn
from devmemory.services.analytics import analytics_summary
from devmemory.services.context import ProjectContext
from devmemory.services.databricks_sync import drain, sync_status


def analytics_command(
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Development intelligence: regressions, feature attempts, file churn, agents, trend."""
    with ProjectContext.load() as ctx:
        summary = analytics_summary(ctx)

    if as_json:
        console.print_json(json.dumps(summary.model_dump(mode="json")))
        return

    console.print()
    console.print(
        f"[bold]{summary.project}[/bold]   "
        f"[dim]source: {summary.source}[/dim]   "
        f"{summary.version_count} versions · {summary.regression_count} regressions · "
        f"{summary.success_rate}% success\n"
    )

    if summary.regressions:
        t = Table(title="Regressions", title_justify="left", box=None, header_style="dim")
        t.add_column("")
        t.add_column("sev")
        t.add_column("feature")
        t.add_column("detail", overflow="fold")
        for r in summary.regressions[:10]:
            t.add_row(r.version_id.upper(), r.severity, r.feature or "-", r.detail)
        console.print(t)
        console.print()

    if summary.features:
        t = Table(title="Feature attempts", title_justify="left", box=None, header_style="dim")
        t.add_column("feature")
        t.add_column("attempts", justify="right")
        t.add_column("success", justify="right")
        t.add_column("regressions", justify="right")
        for feat in summary.features:
            t.add_row(
                feat.feature, str(feat.attempts), f"{feat.success_rate}%", str(feat.regressions)
            )
        console.print(t)
        console.print()

    if summary.file_churn:
        t = Table(title="File churn", title_justify="left", box=None, header_style="dim")
        t.add_column("file")
        t.add_column("changes", justify="right")
        t.add_column("adverse", justify="right")
        for churn in summary.file_churn[:10]:
            t.add_row(churn.path, str(churn.changes), str(churn.adverse_changes))
        console.print(t)
        console.print()

    if summary.agents:
        t = Table(title="Agent effectiveness", title_justify="left", box=None, header_style="dim")
        t.add_column("agent")
        t.add_column("versions", justify="right")
        t.add_column("success", justify="right")
        t.add_column("tokens/success", justify="right")
        for row in summary.agents:
            t.add_row(
                row.agent,
                str(row.versions),
                f"{row.success_rate}%",
                f"{row.tokens_per_success / 1000:.0f}k" if row.tokens_per_success else "-",
            )
        console.print(t)

    if summary.failed_approaches:
        console.print()
        for fa in summary.failed_approaches[:5]:
            console.print(
                f"[red]repeatedly failed[/red] ({fa.occurrences}x) "
                f"{', '.join(fa.signature[:3])}  [dim]{fa.example_intent or ''}[/dim]"
            )


databricks_app = typer.Typer(help="Databricks analytics sync.", no_args_is_help=True)


@databricks_app.command("status")
def databricks_status() -> None:
    """Show Databricks configuration and the pending outbox."""
    with ProjectContext.load() as ctx:
        s = sync_status(ctx)
    console.print(
        f"configured: {s.configured}\n"
        f"detail: {s.detail}\n"
        f"queued: {len(s.queued)}"
        + (f" ({', '.join(x.upper() for x in s.queued)})" if s.queued else "")
    )
    if not s.configured:
        hint(
            "Set DATABRICKS_HOST, DATABRICKS_TOKEN, DATABRICKS_WAREHOUSE_ID, then `devmemory databricks push`."
        )


@databricks_app.command("push")
def databricks_push() -> None:
    """Publish every queued development version to Databricks."""
    with ProjectContext.load() as ctx:
        result = drain(ctx)
    if not result.configured:
        warn(result.detail or "Databricks is not configured.")
        return
    if result.pushed:
        success(f"published {len(result.pushed)}: {', '.join(x.upper() for x in result.pushed)}")
    if result.failed:
        warn(f"failed: {', '.join(result.failed)} — {result.detail}")
    if not result.pushed and not result.failed:
        if result.detail:
            warn(result.detail)
        else:
            console.print("[dim]nothing queued[/dim]")
    if result.queued:
        console.print(Panel(", ".join(x.upper() for x in result.queued), title="still queued"))


__all__ = ["analytics_command", "databricks_app"]
