"""``devmemory show <version>`` - the full development record for one version."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.panel import Panel
from rich.syntax import Syntax

from devmemory.cli._render import console, kv_table, status_text
from devmemory.services.context import ProjectContext
from devmemory.services.versions import get_version


def show_command(
    version: Annotated[str, typer.Argument(help="Version ref: v7, 7, or a commit prefix.")],
    diff: Annotated[bool, typer.Option("--diff", help="Also print the git diff.")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Emit as JSON.")] = False,
) -> None:
    """Show one version: intent, agent, checkpoint, commit, files, tests, metrics, status."""
    with ProjectContext.load() as ctx:
        v = get_version(ctx, version)
        diff_text = ctx.git.diff_text(v.parent_commit, v.git_commit) if diff else None

    if as_json:
        console.print_json(json.dumps(v.model_dump(mode="json")))
        return

    console.print()
    console.print(f"[bold cyan]{v.version_id.upper()}[/bold cyan]  ", status_text(v.status))
    console.print()

    rows: list[tuple[str, object]] = [("intent", v.intent or "-")]
    if v.agent:
        rows.append(("agent", f"{v.agent}" + (f"  ({v.model})" if v.model else "")))
    if v.primary_checkpoint:
        cp = v.primary_checkpoint
        line = f"{cp.checkpoint_id}  [dim]{cp.association_method.value}[/dim]"
        if cp.is_uncertain:
            line += f"  [yellow]confidence {cp.association_confidence:.2f}[/yellow]"
        rows.append(("entire", line))
    rows.append(
        ("commit", f"{v.git_commit[:12]}  [dim](parent {(v.parent_commit or '-')[:12]})[/dim]")
    )
    if v.branch:
        rows.append(("branch", v.branch))
    if v.feature_id:
        rows.append(("feature", v.feature_id.split(":", 1)[-1]))
    rows.append(
        (
            "changes",
            f"{v.files_changed} files   [green]+{v.lines_added}[/green] [red]-{v.lines_removed}[/red]",
        )
    )
    if v.tests and v.tests.ran:
        rows.append(
            (
                "tests",
                f"{v.tests.passed} passed / {v.tests.failed} failed / {v.tests.skipped} skipped",
            )
        )
    if v.committed_at:
        rows.append(("committed", v.committed_at.isoformat(timespec="minutes")))
    console.print(kv_table(rows))

    if v.metrics:
        console.print()
        mt = kv_table(
            (
                m.name,
                f"{m.before} → {m.after}"
                + (f" {m.unit}" if m.unit else "")
                + (
                    "  [green]improvement[/green]"
                    if m.is_improvement
                    else "  [red]worse[/red]"
                    if m.is_worse
                    else ""
                ),
            )
            for m in v.metrics
        )
        console.print(Panel(mt, title="metrics", title_align="left", border_style="dim"))

    if v.changed_files:
        console.print()
        files = "\n".join(
            f"  {_mark(f.change_type.value)} {f.path}"
            + (
                f"  [green]+{f.additions}[/green] [red]-{f.deletions}[/red]"
                if not f.binary
                else "  [dim]binary[/dim]"
            )
            for f in v.changed_files
        )
        console.print(Panel(files, title="files", title_align="left", border_style="dim"))

    if v.regressions:
        console.print()
        for r in v.regressions:
            console.print(f"[bold red]regression[/bold red] {r.metric or r.kind}: {r.detail}")

    if v.analysis and v.analysis.summary:
        console.print()
        body = v.analysis.summary
        if v.analysis.recommendation:
            body += f"\n\n[bold]recommendation:[/bold] {v.analysis.recommendation}"
        console.print(
            Panel(
                body,
                title=f"analysis ([dim]{v.analysis.provider}[/dim])",
                title_align="left",
                border_style="dim",
            )
        )

    if diff_text:
        console.print()
        console.print(Syntax(diff_text, "diff", theme="ansi_dark", word_wrap=False))


def _mark(change_type: str) -> str:
    return {
        "added": "[green]A[/green]",
        "modified": "[yellow]M[/yellow]",
        "deleted": "[red]D[/red]",
        "renamed": "[cyan]R[/cyan]",
        "copied": "[cyan]C[/cyan]",
        "type_changed": "[magenta]T[/magenta]",
    }.get(change_type, "?")


__all__ = ["show_command"]
