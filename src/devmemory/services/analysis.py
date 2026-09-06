"""Generate and store the AI analysis for a version.

Assembles a normalized :class:`AnalysisInput` from facts already on the version
(plus previous attempts and any stored graph impact), runs the provider chain,
and writes the result to the separate ``analysis`` table via
``VersionRepository.replace_analysis`` - which only ever touches interpretive
fields.
"""

from __future__ import annotations

from devmemory.analysis import AnalysisInput, build_providers, run_analysis
from devmemory.analysis.base import AttemptRef, ImpactRef, MetricDelta
from devmemory.domain.models import Analysis, DevelopmentVersion
from devmemory.services.context import ProjectContext
from devmemory.services.memory import MemoryQuery, previous_attempts
from devmemory.services.versions import get_version
from devmemory.storage.graph_impacts import GraphImpactRepository
from devmemory.storage.versions import VersionRepository


def build_analysis_input(ctx: ProjectContext, version: DevelopmentVersion) -> AnalysisInput:
    feature = version.feature_id.split(":", 1)[-1] if version.feature_id else None

    attempts = previous_attempts(
        ctx,
        MemoryQuery(
            files=[f.path for f in version.changed_files],
            feature=feature,
            intent=version.intent,
            limit=5,
        ),
    )
    attempt_refs = [
        AttemptRef(
            version_id=a.version_id,
            status=a.status,
            result=a.result,
            matched_on=a.matched_on,
        )
        for a in attempts
        if a.version_id != version.version_id
    ]

    impact = GraphImpactRepository(ctx.db).get(version.version_id)
    hotspots = (
        [
            ImpactRef(entity=e.name, change_type=e.change_type, dependents=e.dependents_count)
            for e in impact.hotspots
        ]
        if impact
        else []
    )

    diff_excerpt: str | None = None
    if ctx.config.analysis.include_diff:
        text = ctx.git.diff_text(version.parent_commit, version.git_commit)
        if text:
            diff_excerpt = text[: ctx.config.analysis.max_diff_bytes]

    tests = version.tests if version.tests and version.tests.ran else None
    return AnalysisInput(
        version_id=version.version_id,
        intent=version.intent,
        feature=feature,
        agent=version.agent,
        model=version.model,
        status=version.status.value,
        is_adverse=version.status.is_adverse or bool(version.regressions),
        files_changed=version.files_changed,
        lines_added=version.lines_added,
        lines_removed=version.lines_removed,
        changed_paths=[f.path for f in version.changed_files],
        test_summary=(
            f"{tests.passed} passed / {tests.failed} failed / {tests.skipped} skipped"
            if tests
            else None
        ),
        tests_passed=tests.passed if tests else None,
        tests_failed=tests.failed if tests else None,
        metric_deltas=[
            MetricDelta(
                name=m.name,
                before=m.before,
                after=m.after,
                direction=m.direction.value,
                improved=m.is_improvement,
                worsened=m.is_worse,
            )
            for m in version.metrics
        ],
        regressions=[r.detail or f"{r.metric or r.kind} regressed" for r in version.regressions],
        previous_attempts=attempt_refs,
        impact_hotspots=hotspots,
        diff_excerpt=diff_excerpt,
    )


def analyze_version(
    ctx: ProjectContext,
    ref: str,
    *,
    providers: list[str] | None = None,
    persist: bool = True,
) -> Analysis:
    version = get_version(ctx, ref)
    data = build_analysis_input(ctx, version)
    names = providers or ctx.config.analysis.providers
    chain = build_providers(names, model=ctx.config.analysis.model)
    analysis = run_analysis(data, chain)
    if persist:
        VersionRepository(ctx.db).replace_analysis(version.version_id, analysis)
    return analysis


__all__ = ["analyze_version", "build_analysis_input"]
