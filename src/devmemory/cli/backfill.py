"""``devmemory backfill`` - record development versions from existing git history."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from devmemory.cli._render import console, hint, success, warn
from devmemory.services.backfill import backfill_history
from devmemory.services.context import ProjectContext


def backfill_command(
    limit: Annotated[
        int, typer.Option("--limit", "-n", help="Most recent N commits to scan.")
    ] = 200,
    since: Annotated[
        str | None,
        typer.Option("--since", help='Only commits newer than this (e.g. "3 months ago").'),
    ] = None,
    analyze: Annotated[
        bool,
        typer.Option("--analyze", help="Run LLM analysis per commit (slower, uses API credits)."),
    ] = False,
    snapshot: Annotated[
        bool, typer.Option("--snapshot", help="Archive the source tree for each version.")
    ] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Emit the report as JSON.")] = False,
) -> None:
    """Walk the commits that already exist and record any DevMemory has not seen.

    Each is recorded lightweight - git facts, feature, and regression comparison,
    but no test run, snapshot, Entire checkpoint, or (unless --analyze) LLM
    analysis. Commits already recorded are left untouched.
    """
    with ProjectContext.load() as ctx, console.status("Scanning git history…") as st:

        def _progress(i: int, total: int, sha: str) -> None:
            st.update(f"backfilling [{i}/{total}]  {sha[:10]}")

        report = backfill_history(
            ctx,
            limit=limit,
            since=since,
            analyze=analyze,
            snapshot=snapshot,
            on_progress=_progress,
        )

    if as_json:
        console.print_json(json.dumps(report.model_dump(mode="json")))
        return

    if report.scanned == 0:
        console.print("[dim]No commits in range.[/dim]")
        return

    success(
        f"backfill complete - {report.created} new, {report.skipped} already recorded"
        + (f", {report.failed} failed" if report.failed else "")
        + f"  (scanned {report.scanned})"
    )
    for item in report.items:
        if item.error:
            warn(f"{item.commit[:10]}  {item.error}")
    if report.created:
        hint("Open the dashboard (`devmemory serve`) or run `devmemory history` to see them.")


__all__ = ["backfill_command"]
