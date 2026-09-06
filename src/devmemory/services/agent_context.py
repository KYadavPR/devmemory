"""Agent-facing context.

The MCP server and the REST ``/api/agent/*`` endpoints both read from here. The
shapes are small, flat, and JSON-first - built for another AI agent to consume
before it edits code, not for a human dashboard. Facts only: every field is
collected data (Git, Entire, tests, metrics), never an LLM interpretation.
"""

from __future__ import annotations

from pydantic import BaseModel

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
    context_status: str = "COMPLETE"
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
        context_status=(
            v.context_status.value
            if hasattr(v.context_status, "value")
            else str(v.context_status)
        ),
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


def change_guidance(
    ctx: ProjectContext,
    *,
    files: list[str] | None = None,
    intent: str | None = None,
    feature: str | None = None,
) -> ChangeGuidance:
    files = [f for f in (files or []) if f.strip()]
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

    if verdict == PROCEED:
        succeeded = [a for a in attempts if not a.is_adverse]
        if succeeded:
            headline = (
                f"No prior failures in this area. {succeeded[0].version_id.upper()} "
                "changed similar files successfully - use it as a reference."
            )
        else:
            headline = "No related history - this looks like new ground."
    elif verdict == CAUTION:
        headline = (
            f"{len(adverse)} earlier attempt(s) touching this area went wrong. "
            "Review them before proceeding."
        )
    else:
        headline = (
            f"High risk: {len(adverse)} earlier attempt(s) in this exact area failed"
            f"{' - and more than once' if repeated else ''}. "
            "Read the linked versions and address the root cause first."
        )
        recommendations.append(
            "Surface these prior failures to the developer and confirm the approach before editing."
        )

    return ChangeGuidance(
        verdict=verdict,
        headline=headline,
        files=files,
        intent=intent,
        feature=feature,
        related_attempts=attempts,
        warnings=warnings,
        recommendations=recommendations,
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
