"""Agent-facing context.

The MCP server and the REST ``/api/agent/*`` endpoints both read from here. The
shapes are small, flat, and JSON-first - built for another AI agent to consume
before it edits code, not for a human dashboard. Facts only: every field is
collected data (Git, Entire, tests, metrics), never an LLM interpretation.
"""

from __future__ import annotations

from pydantic import BaseModel

from devmemory.adapters.graph import SymbolImpact
from devmemory.domain.enums import VersionStatus
from devmemory.domain.models import DevelopmentVersion
from devmemory.services.context import ProjectContext
from devmemory.services.memory import MemoryQuery, PreviousAttempt, previous_attempts
from devmemory.services.projects import project_status
from devmemory.services.trace import DevelopmentTrace, build_trace
from devmemory.storage.versions import VersionRepository

# verdicts for check_before_change
PROCEED = "proceed"
CAUTION = "caution"
HIGH_RISK = "high-risk"


class VersionBrief(BaseModel):
    """A development version, flattened to what an agent needs to reason about it."""

    version_id: str
    version_number: int
    status: str
    is_adverse: bool
    intent: str | None
    feature: str | None
    agent: str | None
    model: str | None
    git_commit: str
    files_changed: int
    changed_paths: list[str]
    lines_added: int
    lines_removed: int
    tests: str | None
    metrics: list[str]
    regressions: list[str]
    committed_at: str | None


class ProjectBrief(BaseModel):
    project: str
    repo_path: str
    branch: str | None
    head_commit: str | None
    head_subject: str | None
    working_tree_clean: bool
    head_has_version: bool
    entire_installed: bool
    entire_enabled: bool
    version_count: int
    success_rate: float
    open_features: list[str]
    last_regression_id: str | None
    latest: VersionBrief | None
    recent_adverse: list[VersionBrief]
    notes: list[str]


class VersionReport(BaseModel):
    brief: VersionBrief
    trace: DevelopmentTrace
    parent_commit: str | None


class ChangeGuidance(BaseModel):
    """The answer to "should I make this change, and what should I know first?"."""

    verdict: str  # proceed | caution | high-risk
    headline: str
    files: list[str]
    intent: str | None
    feature: str | None
    related_attempts: list[PreviousAttempt]
    warnings: list[str]
    recommendations: list[str]
    # live code-graph blast radius (empty when the graph plugin is unavailable
    # or no symbols were named)
    graph_available: bool = False
    symbol_impacts: list[SymbolImpact] = []
    max_blast_radius: int = 0


# --- builders ------------------------------------------------------------------


def version_brief(v: DevelopmentVersion) -> VersionBrief:
    tests = None
    if v.tests and v.tests.ran:
        tests = f"{v.tests.passed} passed / {v.tests.failed} failed"
        if v.tests.skipped:
            tests += f" / {v.tests.skipped} skipped"
    metrics = [
        (
            f"{m.name}: {m.before:g} -> {m.after:g}"
            if m.before is not None
            else f"{m.name}: {m.after}"
        )
        for m in v.metrics
        if m.after is not None
    ]
    regressions = [r.detail or f"{r.metric or r.kind} regressed" for r in v.regressions]
    return VersionBrief(
        version_id=v.version_id,
        version_number=v.version_number,
        status=v.status.value,
        is_adverse=v.status.is_adverse or bool(v.regressions),
        intent=v.intent,
        feature=v.feature_id.split(":", 1)[-1] if v.feature_id else None,
        agent=v.agent,
        model=v.model,
        git_commit=v.git_commit,
        files_changed=v.files_changed,
        changed_paths=[f.path for f in v.changed_files],
        lines_added=v.lines_added,
        lines_removed=v.lines_removed,
        tests=tests,
        metrics=metrics,
        regressions=regressions,
        committed_at=v.committed_at.isoformat() if v.committed_at else None,
    )


def recent_history(
    ctx: ProjectContext, *, limit: int = 20, feature: str | None = None
) -> list[VersionBrief]:
    versions = VersionRepository(ctx.db).page(
        ctx.config.project_id, limit=max(limit, 1), ascending=False
    )
    if feature:
        want = feature.lower()
        versions = [
            v for v in versions if v.feature_id and v.feature_id.split(":", 1)[-1].lower() == want
        ]
    return [version_brief(v) for v in versions[:limit]]


def project_brief(ctx: ProjectContext) -> ProjectBrief:
    status = project_status(ctx, entire_probe=ctx.entire.probe())
    repo = VersionRepository(ctx.db)
    everything = repo.page(ctx.config.project_id, limit=5000, ascending=True)
    n = len(everything)
    successes = sum(1 for v in everything if v.status is VersionStatus.SUCCESS)

    latest = repo.latest(ctx.config.project_id)
    recent_adverse = [
        version_brief(v) for v in reversed(everything) if v.status.is_adverse or v.regressions
    ][:5]

    notes: list[str] = []
    if not status.head_has_version:
        notes.append(
            "HEAD has no development version yet - run `devmemory checkpoint` after the next change."
        )
    if not status.working_tree_clean:
        notes.append("The working tree has uncommitted changes.")
    if status.last_regression_id:
        notes.append(
            f"The most recent regression is {status.last_regression_id.upper()}; "
            "check it before touching the same area."
        )
    if not status.entire.installed:
        notes.append("Entire is not installed here, so AI-session context may be missing.")

    return ProjectBrief(
        project=status.project.name,
        repo_path=str(ctx.paths.repo_root),
        branch=status.branch,
        head_commit=status.head_sha,
        head_subject=status.head_subject,
        working_tree_clean=status.working_tree_clean,
        head_has_version=status.head_has_version,
        entire_installed=status.entire.installed,
        entire_enabled=status.entire.enabled,
        version_count=n,
        success_rate=round(successes / n * 100, 1) if n else 0.0,
        open_features=status.open_features,
        last_regression_id=status.last_regression_id,
        latest=version_brief(latest) if latest else None,
        recent_adverse=recent_adverse,
        notes=notes,
    )


def version_report(ctx: ProjectContext, ref: str) -> VersionReport:
    from devmemory.services.versions import get_version

    v = get_version(ctx, ref)
    return VersionReport(
        brief=version_brief(v),
        trace=build_trace(v),
        parent_commit=v.parent_commit,
    )


_RANK = {PROCEED: 0, CAUTION: 1, HIGH_RISK: 2}
_BLAST_CAUTION = 8
_BLAST_HIGH_RISK = 20


def _worse(a: str, b: str) -> str:
    return a if _RANK[a] >= _RANK[b] else b


def _graph_blast_radius(
    ctx: ProjectContext, symbols: list[str]
) -> tuple[list[SymbolImpact], list[str], list[str], str]:
    """Run `entire graph impact` for each named symbol. Returns
    (impacts, warnings, recommendations, verdict_floor)."""
    warnings: list[str] = []
    recommendations: list[str] = []
    impacts: list[SymbolImpact] = []
    floor = PROCEED
    if not symbols or not ctx.graph.is_available:
        return impacts, warnings, recommendations, floor

    for sym in symbols:
        si = ctx.graph.symbol_impact(sym)
        if si is None:
            continue
        impacts.append(si)
        if not si.resolved:
            if si.definitions:
                where = ", ".join(f"{d.file_path}:{d.start_line}" for d in si.definitions[:4])
                recommendations.append(f"`{sym}` is ambiguous in the graph - candidates: {where}")
            continue
        if si.callers_total == 0 and si.type_consumers_total == 0:
            continue
        files_hit = [f for f in si.affected_files if f]
        warnings.append(
            f"`{si.query}` has {si.callers_total} caller(s)"
            + (f" + {si.type_consumers_total} type consumer(s)" if si.type_consumers_total else "")
            + (f" across {len(files_hit)} file(s): {', '.join(files_hit[:6])}" if files_hit else "")
        )
        if si.blast_radius >= _BLAST_HIGH_RISK:
            floor = _worse(floor, HIGH_RISK)
            recommendations.append(
                f"`{si.query}` is high fan-out ({si.blast_radius}) - keep its signature/behaviour "
                "stable, or run the full suite and check every caller."
            )
        elif si.blast_radius >= _BLAST_CAUTION:
            floor = _worse(floor, CAUTION)
            recommendations.append(f"Run tests covering the {si.blast_radius} dependents of `{si.query}`.")
    return impacts, warnings, recommendations, floor


def change_guidance(
    ctx: ProjectContext,
    *,
    files: list[str] | None = None,
    intent: str | None = None,
    feature: str | None = None,
    symbols: list[str] | None = None,
) -> ChangeGuidance:
    files = [f for f in (files or []) if f.strip()]
    symbols = [s.strip() for s in (symbols or []) if s.strip()]
    attempts = previous_attempts(
        ctx,
        MemoryQuery(
            files=files,
            intent=intent,
            feature=feature,
            include_successes=True,
            limit=8,
        ),
    )
    adverse = [a for a in attempts if a.is_adverse]

    # a strongly-matching past failure, or the same failure more than once
    strong = [a for a in adverse if a.score >= 4.0]
    repeated = len(adverse) >= 2

    if strong or repeated:
        verdict = HIGH_RISK
    elif adverse:
        verdict = CAUTION
    else:
        verdict = PROCEED

    warnings: list[str] = []
    recommendations: list[str] = []
    for a in adverse:
        label = f"{a.version_id.upper()} [{a.status}]"
        warnings.append(f"{label}: {a.result}  (matched on {', '.join(a.matched_on)})")
        if a.recommendation:
            recommendations.append(f"{a.version_id.upper()}: {a.recommendation}")

    # live code-graph blast radius
    impacts, g_warnings, g_recs, g_floor = _graph_blast_radius(ctx, symbols)
    warnings.extend(g_warnings)
    recommendations.extend(g_recs)
    verdict = _worse(verdict, g_floor)
    max_blast = max((si.blast_radius for si in impacts), default=0)

    blast_clause = f"the code graph shows up to {max_blast} dependents" if max_blast else ""

    if verdict == PROCEED:
        succeeded = [a for a in attempts if not a.is_adverse]
        if succeeded:
            headline = (
                f"No prior failures in this area. {succeeded[0].version_id.upper()} "
                "changed similar files successfully - use it as a reference."
            )
        elif impacts:
            headline = "No related history; low blast radius in the code graph. Looks safe."
        else:
            headline = "No related history - this looks like new ground."
    elif verdict == CAUTION:
        parts = []
        if adverse:
            parts.append(f"{len(adverse)} earlier attempt(s) here went wrong")
        if g_floor != PROCEED:
            parts.append(blast_clause)
        headline = " and ".join(p for p in parts if p) + ". Review before proceeding."
    else:
        parts = []
        if strong or repeated:
            parts.append(
                f"{len(adverse)} earlier attempt(s) in this exact area failed"
                f"{' - and more than once' if repeated else ''}"
            )
            recommendations.append(
                "Surface these prior failures to the developer and confirm the approach before editing."
            )
        if g_floor == HIGH_RISK:
            parts.append(blast_clause)
        headline = "High risk: " + " and ".join(p for p in parts if p) + "."

    return ChangeGuidance(
        verdict=verdict,
        headline=headline,
        files=files,
        intent=intent,
        feature=feature,
        related_attempts=attempts,
        warnings=warnings,
        recommendations=recommendations,
        graph_available=ctx.graph.is_available,
        symbol_impacts=impacts,
        max_blast_radius=max_blast,
    )


__all__ = [
    "CAUTION",
    "HIGH_RISK",
    "PROCEED",
    "ChangeGuidance",
    "ProjectBrief",
    "VersionBrief",
    "VersionReport",
    "change_guidance",
    "project_brief",
    "recent_history",
    "version_brief",
    "version_report",
]
