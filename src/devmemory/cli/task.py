"""``devmemory task`` - drive and inspect the state-aware coding loop.

devmemory task new "add auth with login + password reset" --test "pytest -q"
devmemory task state            # the §19 dashboard for the latest task
devmemory task refresh          # re-collect evidence, print the new state
devmemory task issue "blocked on missing SMTP creds" --blocking
devmemory task complete         # completion evaluation (never blind READY)
devmemory task list / history
"""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table

from devmemory.cli._render import console
from devmemory.domain.enums import RequirementStatus, TaskStatus
from devmemory.domain.taskloop import NormalizedState
from devmemory.services.context import ProjectContext
from devmemory.services.taskloop import engine

task_app = typer.Typer(
    name="task",
    help="The state-aware coding loop: task -> state -> code -> tests -> commit -> refresh.",
    no_args_is_help=True,
)

_STATUS_STYLE = {
    TaskStatus.IN_PROGRESS: "cyan",
    TaskStatus.NEEDS_WORK: "yellow",
    TaskStatus.READY: "bold green",
    TaskStatus.BLOCKED: "bold red",
}
_REQ_STYLE = {
    RequirementStatus.COMPLETE: "green",
    RequirementStatus.PARTIAL: "yellow",
    RequirementStatus.INCOMPLETE: "red",
    RequirementStatus.UNKNOWN: "dim",
}


def _resolve_task_id(ctx: ProjectContext, task_id: str | None) -> str:
    if task_id:
        return task_id
    latest = engine.latest_task(ctx)
    if latest is None:
        raise typer.BadParameter("no tasks yet - create one with `devmemory task new`")
    return latest.id


@task_app.command("new")
def task_new(
    goal: Annotated[str, typer.Argument(help="The human task, in plain language.")],
    test_command: Annotated[
        str | None, typer.Option("--test", "-t", help="Test command (default: tests.command).")
    ] = None,
    push_policy: Annotated[
        str, typer.Option("--push-policy", help="manual | on_ready | never")
    ] = "manual",
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Create a task: normalize the goal into requirements and pin the base commit."""
    with ProjectContext.load() as ctx:
        task = engine.create_task(
            ctx, goal=goal, test_command=test_command, push_policy=push_policy
        )
        state = engine.get_state(ctx, task.id)
    if as_json:
        console.print_json(state.model_dump_json())
        return
    console.print(f"[bold]{task.id}[/bold] created  ·  {len(task.requirements)} requirements")
    for r in task.requirements:
        console.print(f"  [cyan]{r.id}[/cyan]  {r.description}")
    console.print()
    _render_state(state)


@task_app.command("state")
def task_state(
    task_id: Annotated[str | None, typer.Argument()] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show the current stored state for a task (no refresh)."""
    with ProjectContext.load() as ctx:
        tid = _resolve_task_id(ctx, task_id)
        state = engine.get_state(ctx, tid)
    if as_json:
        console.print_json(state.model_dump_json())
        return
    _render_state(state)


@task_app.command("refresh")
def task_refresh(
    task_id: Annotated[str | None, typer.Argument()] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Re-collect evidence, re-evaluate requirements, store a snapshot, print the state."""
    with ProjectContext.load() as ctx:
        tid = _resolve_task_id(ctx, task_id)
        state = engine.refresh_state(ctx, tid)
    if as_json:
        console.print_json(state.model_dump_json())
        return
    _render_state(state)


@task_app.command("complete")
def task_complete(
    task_id: Annotated[str | None, typer.Argument()] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Run a completion evaluation. READY only if the evidence supports it."""
    with ProjectContext.load() as ctx:
        tid = _resolve_task_id(ctx, task_id)
        state = engine.mark_complete(ctx, tid)
    if as_json:
        console.print_json(state.model_dump_json())
        return
    _render_state(state)
    if state.overall_status is not TaskStatus.READY:
        console.print(
            f"\n[yellow]Not READY[/yellow] - {state.overall_status.value}. "
            "Address the findings above and refresh again."
        )


@task_app.command("issue")
def task_issue(
    description: Annotated[str, typer.Argument(help="What is unresolved.")],
    task_id: Annotated[str | None, typer.Option("--task")] = None,
    blocking: Annotated[
        bool, typer.Option("--blocking", help="Cannot continue without a human decision.")
    ] = False,
) -> None:
    """Record an unresolved item. --blocking forces BLOCKED on the next refresh."""
    with ProjectContext.load() as ctx:
        tid = _resolve_task_id(ctx, task_id)
        issue = engine.report_issue(ctx, task_id=tid, description=description, blocking=blocking)
    tag = " [red](blocking)[/red]" if blocking else ""
    console.print(f"issue #{issue.id} recorded for {tid}{tag}")


@task_app.command("resolve")
def task_resolve(
    issue_id: Annotated[int, typer.Argument(help="Issue id from `task state`.")],
) -> None:
    """Mark an unresolved item resolved."""
    with ProjectContext.load() as ctx:
        ok = engine.resolve_issue(ctx, issue_id=issue_id)
    console.print(f"issue #{issue_id} {'resolved' if ok else 'not found or already resolved'}")


@task_app.command("requirement")
def task_requirement(
    requirement_id: Annotated[str, typer.Argument(help="e.g. R1")],
    status: Annotated[
        str, typer.Option("--status", "-s", help="complete|partial|incomplete|unknown")
    ],
    note: Annotated[str, typer.Option("--note", "-m", help="Why (auditable).")] = "",
    task_id: Annotated[str | None, typer.Option("--task")] = None,
) -> None:
    """Record your own verdict for a requirement, then refresh.

    The engine still verifies tests + tree state before it will report READY.
    """
    with ProjectContext.load() as ctx:
        tid = _resolve_task_id(ctx, task_id)
        state = engine.set_requirement_status(
            ctx,
            task_id=tid,
            requirement_id=requirement_id,
            status=RequirementStatus(status.upper()),
            note=note,
        )
    _render_state(state)


@task_app.command("list")
def task_list() -> None:
    """All tasks and their current status."""
    from devmemory.storage.tasks import TaskRepository

    with ProjectContext.load() as ctx:
        tasks = TaskRepository(ctx.db).list_tasks()
    if not tasks:
        console.print("[dim]no tasks yet[/dim]")
        return
    table = Table(box=None, pad_edge=False, header_style="dim")
    table.add_column("", style="bold")
    table.add_column("status")
    table.add_column("reqs", justify="right")
    table.add_column("goal", overflow="ellipsis", max_width=60)
    for t in tasks:
        done = sum(1 for r in t.requirements if r.status is RequirementStatus.COMPLETE)
        style = _STATUS_STYLE.get(t.status, "white")
        table.add_row(
            t.id,
            f"[{style}]{t.status.value}[/{style}]",
            f"{done}/{len(t.requirements)}",
            t.goal,
        )
    console.print(table)


@task_app.command("history")
def task_history(
    task_id: Annotated[str | None, typer.Argument()] = None,
    limit: Annotated[int, typer.Option("--limit", "-n")] = 15,
) -> None:
    """The snapshot trail for a task: snapshot #1 -> #2 -> #3 ..."""
    with ProjectContext.load() as ctx:
        tid = _resolve_task_id(ctx, task_id)
        snaps = engine.list_snapshots(ctx, tid, limit=limit)
    if not snaps:
        console.print("[dim]no snapshots yet - run `devmemory task refresh`[/dim]")
        return
    table = Table(box=None, pad_edge=False, header_style="dim")
    table.add_column("#", justify="right")
    table.add_column("when", no_wrap=True)
    table.add_column("status")
    table.add_column("commit", no_wrap=True)
    table.add_column("tests")
    table.add_column("reqs done", justify="right")
    for s in reversed(snaps):
        st = s.state
        style = _STATUS_STYLE.get(s.overall_status, "white")
        done = sum(1 for r in st.requirements if r.status is RequirementStatus.COMPLETE)
        when = s.created_at.strftime("%m-%d %H:%M") if s.created_at else "-"
        table.add_row(
            str(s.id),
            when,
            f"[{style}]{s.overall_status.value}[/{style}]",
            (st.git.commit_sha or "-")[:8],
            f"{st.tests.passed}/{st.tests.failed}",
            f"{done}/{len(st.requirements)}",
        )
    console.print(table)


# --- the §19 dashboard --------------------------------------------------


def _render_state(state: NormalizedState) -> None:
    st = state.overall_status
    style = _STATUS_STYLE.get(st, "white")
    header = Table.grid(padding=(0, 2))
    header.add_column(style="bold cyan")
    header.add_column()
    header.add_row("TASK", f"{state.task.id}  {state.task.goal}")
    header.add_row("STATUS", f"[{style}]{st.value}[/{style}]")

    done = sum(1 for r in state.requirements if r.status is RequirementStatus.COMPLETE)
    header.add_row("REQUIREMENTS", f"{done} / {len(state.requirements)}")
    header.add_row(
        "CHECKPOINT",
        state.checkpoint.current_id or state.checkpoint.last_committed_id or "[dim]none[/dim]",
    )
    g = state.git
    header.add_row(
        "COMMIT",
        (g.commit_sha or "[dim]none[/dim]")[:12]
        + (f"  [dim]{g.commit_subject}[/dim]" if g.commit_subject else "")
        + ("" if g.working_tree_clean else "  [yellow](dirty)[/yellow]"),
    )
    header.add_row(
        "FILES CHANGED",
        f"{g.files_changed}  ([green]+{g.lines_added}[/green]/[red]-{g.lines_deleted}[/red])",
    )
    t = state.tests
    header.add_row(
        "TESTS",
        f"[green]{t.passed} passed[/green] / [red]{t.failed} failed[/red]  [dim]({t.status.value})[/dim]",
    )
    if state.impact.available:
        header.add_row(
            "IMPACT", f"{state.impact.affected_files} files / {state.impact.affected_tests} tests"
        )
    else:
        header.add_row("IMPACT", f"[dim]unavailable - {state.impact.reason}[/dim]")

    console.print(Panel(header, title="state", border_style=style, title_align="left"))

    rt = Table(box=None, pad_edge=False, header_style="dim")
    rt.add_column("")
    rt.add_column("requirement", overflow="fold")
    rt.add_column("", overflow="fold", style="dim")
    for r in state.requirements:
        rs = _REQ_STYLE.get(r.status, "white")
        rt.add_row(
            f"[{rs}]{r.status.value[:4]}[/{rs}]", f"[cyan]{r.id}[/cyan] {r.description}", r.reason
        )
    console.print(rt)

    if state.unresolved:
        console.print("\n[bold]UNRESOLVED[/bold]")
        for i in state.unresolved:
            tag = " [red](blocking)[/red]" if i.blocking else ""
            console.print(f"  #{i.id} [{i.kind}] {i.description}{tag}")

    if state.recommended_focus:
        console.print("\n[bold]NEXT FOCUS[/bold]")
        for f in state.recommended_focus:
            console.print(f"  - {f}")

    if state.findings and not state.recommended_focus:
        console.print("\n[bold]FINDINGS[/bold]")
        for f in state.findings:
            console.print(f"  - {f}")


def state_command(
    task_id: Annotated[str | None, typer.Argument(help="Task id (default: latest).")] = None,
    refresh: Annotated[
        bool, typer.Option("--refresh", "-r", help="Refresh before showing.")
    ] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show the current loop state (the §19 dashboard). Alias for `devmemory task state`."""
    with ProjectContext.load() as ctx:
        tid = _resolve_task_id(ctx, task_id)
        state = engine.refresh_state(ctx, tid) if refresh else engine.get_state(ctx, tid)
    if as_json:
        console.print(json.dumps(state.model_dump(mode="json"), indent=2))
        return
    _render_state(state)


__all__ = ["state_command", "task_app"]
