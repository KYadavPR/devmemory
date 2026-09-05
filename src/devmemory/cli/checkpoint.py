"""``devmemory checkpoint`` - record the current commit as a development version."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from devmemory.cli._render import console, hint, status_text, success, warn
from devmemory.domain.enums import MetricDirection, VersionStatus
from devmemory.domain.errors import DevMemoryError
from devmemory.domain.models import Metric
from devmemory.pipeline.checkpoint import CheckpointRequest, run_checkpoint
from devmemory.services.context import ProjectContext

_LOWER_IS_BETTER_HINTS = (
    "latency",
    "duration",
    "time",
    "loss",
    "error",
    "cost",
    "memory",
    "p50",
    "p95",
    "p99",
    "rt",
)


def checkpoint_command(
    intent: Annotated[
        str | None,
        typer.Option("--intent", help="What was requested (defaults to the checkpoint)."),
    ] = None,
    feature: Annotated[
        str | None, typer.Option("--feature", "-f", help="Feature area this change belongs to.")
    ] = None,
    agent: Annotated[
        str | None, typer.Option("--agent", help="AI agent, if not read from the checkpoint.")
    ] = None,
    status: Annotated[
        str | None,
        typer.Option("--status", help="Override the derived status (SUCCESS, REGRESSION, ...)."),
    ] = None,
    tests_passed: Annotated[
        int | None, typer.Option("--tests-passed", help="Passing test count (skips the runner).")
    ] = None,
    tests_failed: Annotated[
        int | None, typer.Option("--tests-failed", help="Failing test count (skips the runner).")
    ] = None,
    run_tests: Annotated[
        bool,
        typer.Option("--run-tests/--no-run-tests", help="Run the configured test command."),
    ] = True,
    metrics: Annotated[
        list[str] | None,
        typer.Option(
            "--metric", "-m", help="Metric as name=after or name=before:after (repeatable)."
        ),
    ] = None,
    metrics_file: Annotated[
        str | None,
        typer.Option("--metrics-file", help="Path to a JSON metrics file to read."),
    ] = None,
    errors: Annotated[
        list[str] | None, typer.Option("--error", "-e", help="An error encountered (repeatable).")
    ] = None,
    allow_no_entire: Annotated[
        bool,
        typer.Option("--allow-no-entire", help="Record even without an Entire checkpoint."),
    ] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Re-record the version for this commit in place.")
    ] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Emit the result as JSON.")] = False,
) -> None:
    """Turn the current git commit + its Entire/test/metric context into a Development Version."""
    request = CheckpointRequest(
        intent=intent,
        feature=feature,
        agent=agent,
        status=_parse_status(status),
        tests_passed=tests_passed,
        tests_failed=tests_failed,
        run_tests=run_tests,
        metrics=[_parse_metric(m) for m in (metrics or [])],
        metrics_file=metrics_file,
        errors=list(errors or []),
        allow_no_entire=allow_no_entire,
        force=force,
    )

    with ProjectContext.load() as ctx:
        result = run_checkpoint(ctx, request)

    if as_json:
        console.print_json(
            json.dumps(
                {
                    "created": result.created,
                    "version": result.version.model_dump(mode="json"),
                    "run_id": result.run_log.run_id,
                    "warnings": result.warnings,
                }
            )
        )
        return

    v = result.version
    if not result.created:
        warn(f"{v.version_id} already records commit {v.git_commit[:12]} - nothing to do.")
        hint("Pass --force to re-record it.")
        return

    console.print()
    console.print(
        f"[bold]{v.version_id}[/bold]  ", status_text(v.status), f"  [dim]{v.git_commit[:12]}[/dim]"
    )
    if v.intent:
        console.print(f"  intent   {v.intent}")
    if v.primary_checkpoint:
        cp = v.primary_checkpoint
        marker = (
            ""
            if not cp.is_uncertain
            else f" [yellow](confidence {cp.association_confidence:.2f})[/yellow]"
        )
        console.print(
            f"  entire   {cp.checkpoint_id}  [dim]{cp.association_method.value}[/dim]{marker}"
        )
    if v.agent:
        console.print(f"  agent    {v.agent}" + (f"  [dim]{v.model}[/dim]" if v.model else ""))
    if v.feature_id:
        console.print(f"  feature  {v.feature_id.split(':', 1)[-1]}")
    console.print(
        f"  changes  {v.files_changed} files  "
        f"[green]+{v.lines_added}[/green] [red]-{v.lines_removed}[/red]"
    )
    if v.tests and v.tests.ran:
        console.print(f"  tests    {v.tests.passed} passed / {v.tests.failed} failed")
    for m in v.metrics:
        arrow = "→"
        console.print(
            f"  {m.name:<8} {m.before} {arrow} {m.after}" + (f" {m.unit}" if m.unit else "")
        )

    for w in result.warnings:
        warn(w)
    success(f"recorded {v.version_id}")
    console.print(f"[dim]run log: {result.run_log.run_id}.json[/dim]")


def _parse_status(raw: str | None) -> VersionStatus | None:
    if raw is None:
        return None
    try:
        return VersionStatus(raw.strip().upper())
    except ValueError as exc:
        raise DevMemoryError(
            f"Unknown status {raw!r}.",
            hint=f"One of: {', '.join(s.value for s in VersionStatus)}",
        ) from exc


def _parse_metric(raw: str) -> Metric:
    if "=" not in raw:
        raise DevMemoryError(f"Bad --metric {raw!r}; expected name=after or name=before:after.")
    name, _, value = raw.partition("=")
    name = name.strip()
    before: float | None = None
    if ":" in value:
        before_s, _, after_s = value.partition(":")
        before = _to_float(before_s, raw)
        after = _to_float(after_s, raw)
    else:
        after = _to_float(value, raw)
    direction = (
        MetricDirection.LOWER_IS_BETTER
        if any(h in name.lower() for h in _LOWER_IS_BETTER_HINTS)
        else MetricDirection.HIGHER_IS_BETTER
    )
    return Metric(name=name, before=before, after=after, direction=direction)


def _to_float(text: str, raw: str) -> float:
    try:
        return float(text.strip())
    except ValueError as exc:
        raise DevMemoryError(f"Bad number in --metric {raw!r}.") from exc


__all__ = ["checkpoint_command"]
