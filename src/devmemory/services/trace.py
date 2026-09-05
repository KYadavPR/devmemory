"""The development trace: intent -> agent -> checkpoint -> commit -> files ->
tests -> metrics -> status -> analysis, as an ordered list of nodes the UI draws
as a connected chain.
"""

from __future__ import annotations

from pydantic import BaseModel

from devmemory.domain.models import DevelopmentVersion
from devmemory.services.context import ProjectContext
from devmemory.services.versions import get_version


class TraceNode(BaseModel):
    key: str
    label: str
    value: str
    detail: str | None = None
    source: str
    """intent | agent | entire | git | files | tests | metrics | status | analysis"""
    status: str | None = None


class DevelopmentTrace(BaseModel):
    version_id: str
    nodes: list[TraceNode]


def development_trace(ctx: ProjectContext, ref: str) -> DevelopmentTrace:
    return build_trace(get_version(ctx, ref))


def build_trace(v: DevelopmentVersion) -> DevelopmentTrace:
    nodes: list[TraceNode] = []

    nodes.append(
        TraceNode(
            key="intent",
            label="Intent",
            value=v.intent or "(none recorded)",
            source="intent",
        )
    )

    if v.agent:
        nodes.append(
            TraceNode(
                key="agent",
                label="AI agent",
                value=v.agent,
                detail=v.model,
                source="agent",
            )
        )

    cp = v.primary_checkpoint
    if cp is not None:
        detail = cp.association_method.value
        if cp.is_uncertain:
            detail += f" · confidence {cp.association_confidence:.2f}"
        nodes.append(
            TraceNode(
                key="checkpoint",
                label="Entire checkpoint",
                value=cp.checkpoint_id,
                detail=detail,
                source="entire",
                status="uncertain" if cp.is_uncertain else "linked",
            )
        )
    else:
        nodes.append(
            TraceNode(
                key="checkpoint",
                label="Entire checkpoint",
                value="not available",
                source="entire",
                status="missing",
            )
        )

    nodes.append(
        TraceNode(
            key="commit",
            label="Git commit",
            value=v.git_commit[:12],
            detail=f"parent {(v.parent_commit or '-')[:12]}",
            source="git",
        )
    )

    nodes.append(
        TraceNode(
            key="files",
            label="Files changed",
            value=f"{v.files_changed} file{'s' if v.files_changed != 1 else ''}",
            detail=f"+{v.lines_added} / -{v.lines_removed}",
            source="files",
        )
    )

    if v.tests and v.tests.ran:
        nodes.append(
            TraceNode(
                key="tests",
                label="Tests",
                value=f"{v.tests.passed} passed / {v.tests.failed} failed",
                detail=v.tests.command,
                source="tests",
                status="pass" if v.tests.all_passed else "fail",
            )
        )

    for m in v.metrics:
        status = "up" if m.is_improvement else "down" if m.is_worse else None
        arrow = f"{m.before} → {m.after}" if m.before is not None else str(m.after)
        nodes.append(
            TraceNode(
                key=f"metric:{m.name}",
                label=m.name,
                value=arrow + (f" {m.unit}" if m.unit else ""),
                source="metrics",
                status=status,
            )
        )

    nodes.append(
        TraceNode(
            key="status",
            label="Result",
            value=v.status.value,
            source="status",
            status=v.status.value.lower(),
        )
    )

    if v.analysis and v.analysis.summary:
        nodes.append(
            TraceNode(
                key="analysis",
                label="Analysis",
                value=v.analysis.summary,
                detail=v.analysis.recommendation,
                source="analysis",
            )
        )

    return DevelopmentTrace(version_id=v.version_id, nodes=nodes)


__all__ = ["DevelopmentTrace", "TraceNode", "build_trace", "development_trace"]
